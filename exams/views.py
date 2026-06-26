import random
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.authentication import CsrfExemptSessionAuthentication
from accounts.permissions import NoTokenAuthOnGameplay

from .csv_io import CsvImportError, decode_csv_upload, export_bank_to_csv, import_csv, replace_bank_questions
from .models import (
    AppSettings, Exam, ExamInstance, ExamInstanceAnswer,
    GradeScale, InProgressInstance, Option, Question, QuestionBank,
)
from .sanitize import sanitize_html


def _require_perm(request, perm):
    if not request.user.has_perm(perm):
        raise exceptions.PermissionDenied(f'Missing permission: {perm}')


def _can_edit_bank(user, bank):
    return user.is_staff or bank.owner_id == user.id


def _require_bank_owner(request, bank):
    if not _can_edit_bank(request.user, bank):
        raise exceptions.PermissionDenied('Only the bank owner or an admin can edit this bank.')


def _can_edit_exam(user, exam):
    return user.is_staff or exam.owner_id == user.id


def _require_exam_owner(request, exam):
    if not _can_edit_exam(request.user, exam):
        raise exceptions.PermissionDenied('Only the exam owner or an admin can edit this exam.')


def _accessible_exams_q(user):
    return Q(allowed_groups__isnull=True) | Q(owner=user) | Q(allowed_groups__in=user.groups.all())


def _require_exam_access(request, exam):
    user = request.user
    if user.is_staff or exam.owner_id == user.id:
        return
    allowed_group_ids = set(exam.allowed_groups.values_list('id', flat=True))
    if allowed_group_ids and not (allowed_group_ids & set(user.groups.values_list('id', flat=True))):
        raise exceptions.PermissionDenied("You don't have access to this exam.")


# ---- Question Banks ----

@extend_schema(methods=['GET'], tags=['Banks'], summary='List question banks', responses={200: OpenApiTypes.OBJECT})
@extend_schema(methods=['POST'], tags=['Banks'], summary='Create bank from CSV', responses={201: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def bank_list(request):
    if request.method == 'POST':
        _require_perm(request, 'exams.add_exam')
        upload = request.FILES.get('file')
        if not upload:
            return Response({'error': 'CSV file is required.'}, status=400)
        name = (request.data.get('name') or upload.name.rsplit('.csv', 1)[0]).strip()
        if not name:
            return Response({'error': 'Bank name is required.'}, status=400)
        if QuestionBank.objects.filter(name__iexact=name).exists():
            return Response({'error': f'A bank named "{name}" already exists.'}, status=400)
        try:
            csv_text = decode_csv_upload(upload)
            bank_id, question_count = import_csv(csv_text, name, upload.name, owner=request.user)
        except CsvImportError as exc:
            return Response({'error': str(exc)}, status=400)
        return Response({'bank_id': bank_id, 'question_count': question_count}, status=201)

    _require_perm(request, 'exams.add_exam')
    qs = QuestionBank.objects.all() if request.user.is_staff else QuestionBank.objects.filter(owner=request.user)
    banks = qs.annotate(question_count=Count('questions')).order_by('-created_at')
    data = [
        {
            'id': b.id,
            'name': b.name,
            'keywords': b.keywords,
            'question_count': b.question_count,
            'created_at': b.created_at,
            'can_edit': _can_edit_bank(request.user, b),
        }
        for b in banks
    ]
    return Response(data)


@extend_schema(tags=['Banks'], summary='Delete bank', responses={204: None})
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def bank_detail(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id)
    _require_bank_owner(request, bank)
    bank.delete()
    return Response(status=204)


@extend_schema(tags=['Banks'], summary='Export bank as CSV', responses={(200, 'text/csv'): OpenApiTypes.STR})
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def bank_export(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id)
    _require_bank_owner(request, bank)
    csv_text = export_bank_to_csv(bank)
    filename = ''.join(c if c.isalnum() or c in '_-' else '_' for c in bank.name) + '.csv'
    response = HttpResponse(csv_text, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@extend_schema(tags=['Banks'], summary='Replace bank questions via CSV', responses={200: OpenApiTypes.OBJECT})
@api_view(['PUT'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def bank_import(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id)
    _require_bank_owner(request, bank)
    upload = request.FILES.get('file')
    if not upload:
        return Response({'error': 'CSV file is required.'}, status=400)
    try:
        csv_text = decode_csv_upload(upload)
        question_count = replace_bank_questions(bank, csv_text)
    except CsvImportError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'question_count': question_count})


@extend_schema(tags=['Banks'], summary='List distinct categories in a bank', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bank_categories(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id)
    if not _can_edit_bank(request.user, bank):
        has_access = Exam.objects.filter(
            question_bank=bank
        ).filter(_accessible_exams_q(request.user)).exists()
        if not has_access:
            raise exceptions.PermissionDenied('No access to this bank.')
    rows = (
        bank.questions.values('category')
        .annotate(count=Count('id'))
        .order_by('category')
    )
    return Response([{'category': r['category'], 'count': r['count']} for r in rows])


@extend_schema(methods=['GET'], tags=['Banks'], summary='List bank questions', responses={200: OpenApiTypes.OBJECT})
@extend_schema(methods=['POST'], tags=['Banks'], summary='Add question to bank', responses={201: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def bank_questions(request, bank_id):
    bank = get_object_or_404(QuestionBank, id=bank_id)

    if request.method == 'GET':
        _require_bank_owner(request, bank)
        questions = [_load_question_detail(q) for q in bank.questions.order_by('sort_order')]
        return Response({
            'bank_id': bank.id,
            'bank_name': bank.name,
            'keywords': bank.keywords,
            'can_edit': _can_edit_bank(request.user, bank),
            'questions': questions,
        })

    _require_bank_owner(request, bank)
    try:
        payload = _validate_question_payload(request.data)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)

    with transaction.atomic():
        max_sort = bank.questions.aggregate(m=Max('sort_order'))['m']
        question = Question.objects.create(
            bank=bank,
            category=sanitize_html((request.data.get('category') or '').strip()),
            question_text=payload['question_text'],
            question_type=payload['question_type'],
            points=payload['points'],
            image_link=payload['image_link'],
            explanation=payload['explanation'],
            sort_order=(max_sort + 1) if max_sort is not None else 0,
        )
        Option.objects.bulk_create([
            Option(question=question, option_text=o['text'], is_correct=o['is_correct'], sort_order=idx)
            for idx, o in enumerate(payload['options'])
        ])

    return Response(_load_question_detail(question), status=201)


# ---- Exam Configs ----

@extend_schema(methods=['GET'], tags=['Exams'], summary='List accessible exam configs', responses={200: OpenApiTypes.OBJECT})
@extend_schema(methods=['POST'], tags=['Exams'], summary='Create exam config', responses={201: OpenApiTypes.OBJECT})
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def exam_list(request):
    if request.method == 'POST':
        _require_perm(request, 'exams.add_exam')
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Exam name is required.'}, status=400)
        if Exam.objects.filter(name__iexact=name).exists():
            return Response({'error': f'An exam named "{name}" already exists.'}, status=400)

        bank_id = request.data.get('question_bank_id')
        bank = get_object_or_404(QuestionBank, id=bank_id) if bank_id else None
        if bank and not _can_edit_bank(request.user, bank):
            raise exceptions.PermissionDenied('You do not own this question bank.')

        try:
            question_count = max(1, int(request.data.get('question_count') or 10))
        except (TypeError, ValueError):
            question_count = 10

        category_weights = request.data.get('category_weights')
        if not isinstance(category_weights, dict):
            category_weights = {}

        group_ids = request.data.get('group_ids', [])

        exam = Exam.objects.create(
            name=name,
            question_bank=bank,
            question_count=question_count,
            category_weights=category_weights,
            owner=request.user,
        )
        if group_ids:
            exam.allowed_groups.set(group_ids)
        return Response({'exam_id': exam.id}, status=201)

    _require_perm(request, 'exams.view_exam')
    accessible_ids = Exam.objects.filter(_accessible_exams_q(request.user)).values_list('id', flat=True).distinct()
    exams = list(
        Exam.objects.filter(id__in=list(accessible_ids))
        .select_related('question_bank')
        .order_by('-created_at')
    )
    instances = ExamInstance.objects.filter(exam__in=exams, user=request.user).order_by('exam_id', '-finished_at').values(
        'exam_id', 'num_correct', 'num_questions', 'points_earned', 'total_points',
    )
    last_instances = {}
    for a in instances:
        last_instances.setdefault(a['exam_id'], a)
    instance_counts = dict(
        ExamInstance.objects.filter(exam__in=exams, user=request.user)
        .values_list('exam_id').annotate(c=Count('id'))
    )
    progress_by_exam = {
        p.exam_id: p for p in InProgressInstance.objects.filter(exam__in=exams, user=request.user)
    }

    is_admin = request.user.is_staff
    data = []
    for exam in exams:
        last = last_instances.get(exam.id)
        item = {
            'id': exam.id,
            'name': exam.name,
            'created_at': exam.created_at,
            'question_bank_id': exam.question_bank_id,
            'question_bank_name': exam.question_bank.name if exam.question_bank else None,
            'bonus_window_seconds': exam.bonus_window_seconds,
            'question_count': exam.question_count,
            'category_weights': exam.category_weights,
            'grade_scale_id': exam.grade_scale_id,
            'can_edit': is_admin or exam.owner_id == request.user.id,
            'last_score': last['num_correct'] if last else None,
            'last_total': last['num_questions'] if last else None,
            'last_points_earned': last['points_earned'] if last else None,
            'last_total_points': last['total_points'] if last else None,
            'instance_count': instance_counts.get(exam.id, 0),
        }
        progress = progress_by_exam.get(exam.id)
        if progress:
            answered = [c[1] for c in progress.checked_json if c[1] is not None]
            item['progress_index'] = progress.current_index
            item['progress_total'] = progress.total_questions
            item['progress_num_checked'] = len(answered)
            item['progress_num_correct'] = sum(1 for c in answered if c.get('isCorrect'))
            item['progress_points_earned'] = sum((c.get('pointsAwarded') or c.get('points_awarded') or 0) for c in answered)
        data.append(item)

    return Response(data)


@extend_schema(tags=['Exams'], summary='Delete exam config', responses={204: None})
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def exam_detail(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_owner(request, exam)
    exam.delete()
    return Response(status=204)


@extend_schema(tags=['Exams'], summary='Update exam config settings', responses={200: OpenApiTypes.OBJECT})
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def exam_settings(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_owner(request, exam)

    name = (request.data.get('name') or '').strip()
    if name and name.lower() != exam.name.lower():
        if Exam.objects.filter(name__iexact=name).exclude(id=exam.id).exists():
            return Response({'error': f'An exam named "{name}" already exists.'}, status=400)
        exam.name = name

    try:
        bonus_window_seconds = int(request.data.get('bonus_window_seconds'))
    except (TypeError, ValueError):
        bonus_window_seconds = None
    if bonus_window_seconds is not None and bonus_window_seconds >= 1:
        exam.bonus_window_seconds = bonus_window_seconds

    try:
        question_count = max(1, int(request.data.get('question_count')))
        exam.question_count = question_count
    except (TypeError, ValueError):
        pass

    category_weights = request.data.get('category_weights')
    if isinstance(category_weights, dict):
        exam.category_weights = category_weights

    grade_scale_id = request.data.get('grade_scale_id')
    if grade_scale_id is not None:
        exam.grade_scale_id = grade_scale_id if grade_scale_id else None

    bank_id = request.data.get('question_bank_id')
    if bank_id is not None:
        if bank_id:
            bank = get_object_or_404(QuestionBank, id=bank_id)
            if not _can_edit_bank(request.user, bank):
                raise exceptions.PermissionDenied('You do not own this question bank.')
            exam.question_bank = bank
        else:
            exam.question_bank = None

    exam.save()

    allowed_group_ids = request.data.get('allowed_group_ids')
    if isinstance(allowed_group_ids, list):
        exam.allowed_groups.set(Group.objects.filter(id__in=allowed_group_ids))

    return Response({
        'id': exam.id,
        'name': exam.name,
        'bonus_window_seconds': exam.bonus_window_seconds,
        'question_count': exam.question_count,
        'category_weights': exam.category_weights,
        'question_bank_id': exam.question_bank_id,
        'allowed_group_ids': list(exam.allowed_groups.values_list('id', flat=True)),
        'grade_scale_id': exam.grade_scale_id,
    })


# ---- Editing bank questions ----

def _load_question_detail(question):
    return {
        'id': question.id,
        'bank_id': question.bank_id,
        'category': question.category,
        'question_text': question.question_text,
        'question_type': question.question_type,
        'points': question.points,
        'image_link': question.image_link,
        'explanation': question.explanation,
        'options': [
            {'id': o.id, 'text': o.option_text, 'is_correct': o.is_correct}
            for o in question.options.order_by('sort_order')
        ],
    }


def _validate_question_payload(data):
    question_text = (data.get('question_text') or '').strip()
    if not question_text:
        raise ValueError('Question text is required.')

    question_type = Question.MULTI if data.get('question_type') == 'multi' else Question.SINGLE
    raw_options = data.get('options') if isinstance(data.get('options'), list) else []
    options = [
        {'text': (o.get('text') or '').strip(), 'is_correct': bool(o.get('is_correct'))}
        for o in raw_options
    ]
    options = [o for o in options if o['text']]

    if len(options) < 2:
        raise ValueError('At least 2 options are required.')
    correct_count = sum(1 for o in options if o['is_correct'])
    if correct_count == 0:
        raise ValueError('At least one option must be marked correct.')
    if question_type == Question.SINGLE and correct_count > 1:
        raise ValueError('Single choice questions can only have one correct option.')

    try:
        points = int(data.get('points'))
    except (TypeError, ValueError):
        points = 0
    points = points if points > 0 else 1

    return {
        'question_text': sanitize_html(question_text),
        'question_type': question_type,
        'points': points,
        'image_link': (data.get('image_link') or '').strip() or None,
        'explanation': sanitize_html((data.get('explanation') or '').strip()) or None,
        'options': [{'text': sanitize_html(o['text']), 'is_correct': o['is_correct']} for o in options],
    }


@extend_schema(methods=['PUT'], tags=['Banks'], summary='Update question', responses={200: OpenApiTypes.OBJECT})
@extend_schema(methods=['DELETE'], tags=['Banks'], summary='Delete question', responses={204: None})
@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_detail(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    _require_bank_owner(request, question.bank)

    if request.method == 'DELETE':
        question.delete()
        return Response(status=204)

    try:
        payload = _validate_question_payload(request.data)
    except ValueError as exc:
        return Response({'error': str(exc)}, status=400)

    with transaction.atomic():
        question.category = sanitize_html((request.data.get('category') or '').strip())
        question.question_text = payload['question_text']
        question.question_type = payload['question_type']
        question.points = payload['points']
        question.image_link = payload['image_link']
        question.explanation = payload['explanation']
        question.save()
        question.options.all().delete()
        Option.objects.bulk_create([
            Option(question=question, option_text=o['text'], is_correct=o['is_correct'], sort_order=idx)
            for idx, o in enumerate(payload['options'])
        ])

    return Response(_load_question_detail(question))


# ---- Taking an exam ----

@extend_schema(exclude=True)
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def exam_start(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_access(request, exam)

    has_existing = InProgressInstance.objects.filter(exam=exam, user=request.user).exists()
    if not has_existing:
        max_instances = AppSettings.get_solo().max_in_progress_instances
        if max_instances > 0:
            if InProgressInstance.objects.filter(user=request.user).count() >= max_instances:
                return Response({
                    'error': (
                        f"You've reached the maximum of {max_instances} in-progress exam instance(s). "
                        'Finish or delete an existing instance before starting a new one.'
                    ),
                }, status=400)

    selected = exam.sample_questions()
    if not selected:
        return Response({'error': 'This exam has no questions available to sample.'}, status=400)

    questions = []
    for q in selected:
        options = random.sample(opts := list(q.options.all()), len(opts))
        select_count = q.options.filter(is_correct=True).count() if q.question_type == Question.MULTI else 1
        questions.append({
            'id': q.id,
            'question_text': q.question_text,
            'question_type': q.question_type,
            'image_link': q.image_link,
            'points': q.points,
            'category': q.category,
            'select_count': select_count,
            'options': [{'id': o.id, 'text': o.option_text} for o in options],
        })

    return Response({
        'exam_id': exam.id,
        'exam_name': exam.name,
        'bonus_window_seconds': exam.bonus_window_seconds,
        'questions': questions,
    })


# ---- Resumable in-progress state ----

@extend_schema(exclude=True)
@api_view(['PUT', 'GET', 'DELETE'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def exam_progress(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_access(request, exam)

    if request.method == 'DELETE':
        InProgressInstance.objects.filter(exam=exam, user=request.user).delete()
        return Response(status=204)

    if request.method == 'GET':
        row = InProgressInstance.objects.filter(exam=exam, user=request.user).first()
        if not row:
            return Response({'error': 'No saved progress for this exam.'}, status=404)
        return Response({
            'exam_id': row.exam_id,
            'exam_name': exam.name,
            'bonus_window_seconds': exam.bonus_window_seconds,
            'questions': row.questions_json,
            'answers': row.answers_json,
            'checked': row.checked_json,
            'elapsed_seconds': row.elapsed_seconds_json,
            'index': row.current_index,
            'total_questions': row.total_questions,
            'started_at': row.started_at,
            'multiplier': row.multiplier,
        })

    questions = request.data.get('questions')
    answers = request.data.get('answers')
    checked = request.data.get('checked')
    if not isinstance(questions, list) or not isinstance(answers, list) or not isinstance(checked, list):
        return Response({'error': 'questions, answers, and checked arrays are required.'}, status=400)

    started_at = request.data.get('started_at') or datetime.now(dt_timezone.utc).isoformat()
    if isinstance(started_at, str):
        started_at = parse_datetime(started_at) or datetime.now(dt_timezone.utc)

    elapsed_seconds = request.data.get('elapsed_seconds')
    InProgressInstance.objects.update_or_create(
        exam=exam,
        user=request.user,
        defaults={
            'questions_json': questions,
            'answers_json': answers,
            'checked_json': checked,
            'elapsed_seconds_json': elapsed_seconds if isinstance(elapsed_seconds, list) else [],
            'current_index': int(request.data.get('index') or 0),
            'total_questions': len(questions),
            'started_at': started_at,
            'multiplier': int(request.data.get('multiplier') or 1),
        },
    )
    return Response(status=204)


@extend_schema(exclude=True)
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def question_check(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    # Verify user has access to at least one exam sourced from this bank
    accessible = Exam.objects.filter(
        question_bank=question.bank,
    ).filter(_accessible_exams_q(request.user)).exists()
    if not accessible:
        raise exceptions.PermissionDenied("You don't have access to this question.")

    options = list(question.options.all())
    correct_ids = {str(o.id) for o in options if o.is_correct}
    selected_ids = request.data.get('selected_option_ids')
    selected_ids = {str(i) for i in selected_ids} if isinstance(selected_ids, list) else set()

    return Response({
        'is_correct': correct_ids == selected_ids,
        'correct_option_ids': list(correct_ids),
        'explanation': question.explanation,
    })


@extend_schema(exclude=True)
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def exam_submit(request, exam_id):
    exam = get_object_or_404(Exam.objects.select_related('grade_scale', 'question_bank'), id=exam_id)
    _require_exam_access(request, exam)
    answers = request.data.get('answers')
    if not isinstance(answers, list) or not answers:
        return Response({'error': 'answers array is required.'}, status=400)

    started_at = request.data.get('started_at') or datetime.now(dt_timezone.utc).isoformat()
    if isinstance(started_at, str):
        started_at = parse_datetime(started_at) or datetime.now(dt_timezone.utc)

    results = []
    num_correct = 0
    total_points = 0
    points_earned = 0

    for answer in answers:
        # Verify question belongs to this exam's bank
        question = Question.objects.filter(id=answer.get('question_id'), bank=exam.question_bank).first()
        if not question:
            continue
        options = list(question.options.order_by('sort_order'))
        correct_ids = {str(o.id) for o in options if o.is_correct}
        selected_ids_raw = answer.get('selected_option_ids')
        selected_ids = [str(i) for i in selected_ids_raw] if isinstance(selected_ids_raw, list) else []

        is_correct = correct_ids == set(selected_ids)
        if is_correct:
            num_correct += 1
        total_points += question.points

        try:
            points_awarded = max(0, round(float(answer.get('points_awarded'))))
        except (TypeError, ValueError):
            points_awarded = question.points if is_correct else 0
        points_earned += points_awarded

        results.append({
            'question_id': question.id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'image_link': question.image_link,
            'explanation': question.explanation,
            'points': question.points,
            'points_awarded': points_awarded,
            'is_correct': is_correct,
            'selected_option_ids': selected_ids,
            'options': [{'id': o.id, 'text': o.option_text, 'is_correct': o.is_correct} for o in options],
        })

    grade = None
    if exam.grade_scale_id:
        pct = round(num_correct / len(answers) * 100) if answers else 0
        grade = exam.grade_scale.compute_grade(pct) or 'N/A'

    with transaction.atomic():
        instance = ExamInstance.objects.create(
            exam=exam,
            user=request.user,
            started_at=started_at,
            num_questions=len(answers),
            num_correct=num_correct,
            total_points=total_points,
            points_earned=points_earned,
            grade=grade,
            grade_scale=exam.grade_scale,
        )
        ExamInstanceAnswer.objects.bulk_create([
            ExamInstanceAnswer(
                instance=instance,
                question_id=r['question_id'],
                selected_option_ids=r['selected_option_ids'],
                is_correct=r['is_correct'],
                points_awarded=r['points_awarded'],
            )
            for r in results
        ])
        InProgressInstance.objects.filter(exam=exam, user=request.user).delete()

    return Response({
        'instance_id': instance.id,
        'exam_id': exam.id,
        'exam_name': exam.name,
        'num_questions': len(answers),
        'num_correct': num_correct,
        'total_points': total_points,
        'points_earned': points_earned,
        'grade': instance.grade,
        'results': results,
    })


# ---- Instance history ----

@extend_schema(tags=['Exams'], summary='List instances for an exam', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exam_instances(request, exam_id):
    qs = ExamInstance.objects.filter(exam_id=exam_id)
    if not request.user.has_perm('exams.view_examinstance'):
        qs = qs.filter(user=request.user)
    return Response(list(qs.order_by('-finished_at').values(
        'id', 'started_at', 'finished_at', 'num_questions', 'num_correct', 'total_points', 'points_earned', 'grade',
    )))


@extend_schema(tags=['Exams'], summary='Get instance detail', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def instance_detail(request, instance_id):
    instance = get_object_or_404(ExamInstance.objects.select_related('exam', 'user'), id=instance_id)
    user = request.user
    can_view = (
        instance.user_id == user.id
        or user.is_staff
        or user.has_perm('exams.view_examinstance')
        or (user.has_perm('exams.add_exam') and instance.exam.owner_id == user.id)
    )
    if not can_view:
        raise exceptions.PermissionDenied('Missing permission: exams.view_examinstance')

    results = []
    for a in instance.answers.all():
        question = a.question
        options = question.options.order_by('sort_order')
        results.append({
            'question_id': a.question_id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'image_link': question.image_link,
            'explanation': question.explanation,
            'points': question.points,
            'points_awarded': a.points_awarded,
            'is_correct': a.is_correct,
            'selected_option_ids': a.selected_option_ids,
            'options': [{'id': o.id, 'text': o.option_text, 'is_correct': o.is_correct} for o in options],
        })

    return Response({
        'id': instance.id,
        'exam_id': instance.exam_id,
        'exam_name': instance.exam.name,
        'user': instance.user.username,
        'started_at': instance.started_at,
        'finished_at': instance.finished_at,
        'num_questions': instance.num_questions,
        'num_correct': instance.num_correct,
        'total_points': instance.total_points,
        'points_earned': instance.points_earned,
        'grade': instance.grade,
        'grade_log': instance.grade_log,
        'results': results,
    })


# ---- Global ----

@extend_schema(tags=['Exams'], summary='List groups', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def group_list(request):
    return Response(list(Group.objects.order_by('name').values('id', 'name')))


@extend_schema(tags=['Exams'], summary='List grade scales', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def grade_scale_list(request):
    return Response(list(GradeScale.objects.order_by('name').values('id', 'name', 'entries_json')))


@extend_schema(methods=['GET'], tags=['Exams'], summary='Get app settings', responses={200: OpenApiTypes.OBJECT})
@extend_schema(methods=['PUT'], tags=['Exams'], summary='Update app settings', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def app_settings(request):
    settings_row = AppSettings.get_solo()
    if request.method == 'PUT':
        _require_perm(request, 'exams.change_appsettings')
        settings_row.sound_effects_enabled = bool(request.data.get('sound_effects_enabled'))
        settings_row.theme = 'light' if request.data.get('theme') == 'light' else 'dark'
        try:
            max_instances = int(request.data.get('max_in_progress_instances'))
        except (TypeError, ValueError):
            max_instances = None
        settings_row.max_in_progress_instances = max_instances if max_instances is not None and max_instances >= 0 else 0
        settings_row.save()

    return Response({
        'sound_effects_enabled': settings_row.sound_effects_enabled,
        'theme': settings_row.theme,
        'max_in_progress_instances': settings_row.max_in_progress_instances,
    })
