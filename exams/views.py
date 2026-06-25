import random
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as rf_serializers
from rest_framework import exceptions
from rest_framework.decorators import api_view, authentication_classes, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.authentication import CsrfExemptSessionAuthentication
from accounts.permissions import NoTokenAuthOnGameplay

from .csv_io import CsvImportError, export_exam_to_csv, import_csv, replace_exam_questions
from .models import AppSettings, Attempt, AttemptAnswer, Exam, InProgressAttempt, Option, Question
from .sanitize import sanitize_html


def _require_perm(request, perm):
    if not request.user.has_perm(perm):
        raise exceptions.PermissionDenied(f'Missing permission: {perm}')


def _accessible_exams_q(user):
    """Visibility rule: an exam with no allowed_groups is public (today's
    behavior); otherwise it's visible to its owner, admins, and members of
    any assigned group."""
    return Q(allowed_groups__isnull=True) | Q(owner=user) | Q(allowed_groups__in=user.groups.all())


def _can_edit_exam(user, exam):
    return user.is_staff or exam.owner_id == user.id


def _require_exam_access(request, exam):
    user = request.user
    if user.is_staff or exam.owner_id == user.id:
        return
    allowed_group_ids = set(exam.allowed_groups.values_list('id', flat=True))
    if allowed_group_ids and not (allowed_group_ids & set(user.groups.values_list('id', flat=True))):
        raise exceptions.PermissionDenied("You don't have access to this exam.")


def _require_exam_owner(request, exam):
    if not _can_edit_exam(request.user, exam):
        raise exceptions.PermissionDenied('Only the exam owner or an admin can edit this exam.')


# ---- Exam library ----

@extend_schema(
    methods=['GET'], tags=['Exams'], summary='List accessible exams',
    description='Returns exams visible to the current user. Requires exams.view_exam permission. '
                'Includes in-progress state and last-attempt scores per exam.',
    responses={200: inline_serializer('ExamListItem', fields={
        'id': rf_serializers.IntegerField(),
        'name': rf_serializers.CharField(),
        'created_at': rf_serializers.DateTimeField(),
        'keywords': rf_serializers.CharField(),
        'question_count': rf_serializers.IntegerField(),
        'can_edit': rf_serializers.BooleanField(),
        'last_score': rf_serializers.IntegerField(allow_null=True),
        'last_total': rf_serializers.IntegerField(allow_null=True),
        'last_points_earned': rf_serializers.IntegerField(allow_null=True),
        'last_total_points': rf_serializers.IntegerField(allow_null=True),
        'attempt_count': rf_serializers.IntegerField(),
    }, many=True)},
)
@extend_schema(
    methods=['POST'], tags=['Exams'], summary='Create exam from CSV',
    description='Upload a CSV file to create a new exam. Requires exams.add_exam permission. '
                'Optionally restrict visibility to specific group IDs.',
    request=inline_serializer('ExamImportRequest', fields={
        'file': rf_serializers.FileField(),
        'name': rf_serializers.CharField(required=False),
        'group_ids': rf_serializers.ListField(child=rf_serializers.IntegerField(), required=False),
    }),
    responses={201: inline_serializer('ExamCreated', fields={
        'exam_id': rf_serializers.IntegerField(),
        'question_count': rf_serializers.IntegerField(),
    })},
)
@api_view(['GET', 'POST'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def exam_list(request):
    if request.method == 'POST':
        _require_perm(request, 'exams.add_exam')
        upload = request.FILES.get('file')
        if not upload:
            return Response({'error': 'CSV file is required.'}, status=400)
        name = (request.data.get('name') or upload.name.rsplit('.csv', 1)[0]).strip()
        if not name:
            return Response({'error': 'Exam name is required.'}, status=400)
        if Exam.objects.filter(name__iexact=name).exists():
            return Response({'error': f'An exam named "{name}" already exists.'}, status=400)
        group_ids = [int(i) for i in request.data.getlist('group_ids') if str(i).isdigit()]
        try:
            csv_text = upload.read().decode('utf-8')
            exam_id, question_count = import_csv(
                csv_text, name, upload.name, owner=request.user, group_ids=group_ids,
            )
        except CsvImportError as exc:
            return Response({'error': str(exc)}, status=400)
        return Response({'exam_id': exam_id, 'question_count': question_count}, status=201)

    _require_perm(request, 'exams.view_exam')
    # Resolve accessible exam ids in a separate query first - filtering and
    # annotating in one go would join the allowed_groups M2M table, multiplying
    # rows and throwing off the question_count aggregate.
    accessible_ids = Exam.objects.filter(_accessible_exams_q(request.user)).values_list('id', flat=True).distinct()
    exams = list(
        Exam.objects.filter(id__in=list(accessible_ids))
        .annotate(question_count=Count('questions'))
        .order_by('-created_at')
    )
    _attempts = Attempt.objects.filter(exam__in=exams, user=request.user).order_by(
        'exam_id', '-finished_at'
    ).values('exam_id', 'num_correct', 'num_questions', 'points_earned', 'total_points')
    last_attempts = {}
    for a in _attempts:
        last_attempts.setdefault(a['exam_id'], a)
    progress_by_exam = {
        p.exam_id: p
        for p in InProgressAttempt.objects.filter(exam__in=exams, user=request.user)
    }
    attempt_counts = dict(
        Attempt.objects.filter(exam__in=exams, user=request.user)
        .values_list('exam_id')
        .annotate(c=Count('id'))
    )

    is_admin = request.user.is_staff
    data = []
    for exam in exams:
        last_attempt = last_attempts.get(exam.id)
        item = {
            'id': exam.id,
            'name': exam.name,
            'created_at': exam.created_at,
            'keywords': exam.keywords,
            'question_count': exam.question_count,
            'can_edit': is_admin or exam.owner_id == request.user.id,
            'last_score': last_attempt['num_correct'] if last_attempt else None,
            'last_total': last_attempt['num_questions'] if last_attempt else None,
            'last_points_earned': last_attempt['points_earned'] if last_attempt else None,
            'last_total_points': last_attempt['total_points'] if last_attempt else None,
            'attempt_count': attempt_counts.get(exam.id, 0),
        }
        progress = progress_by_exam.get(exam.id)
        if progress:
            checked = [c[1] for c in progress.checked_json]
            item['progress_index'] = progress.current_index
            item['progress_total'] = progress.total_questions
            item['progress_num_checked'] = len(checked)
            item['progress_num_correct'] = sum(1 for c in checked if c.get('isCorrect') or c.get('is_correct'))
            item['progress_points_earned'] = sum((c.get('pointsAwarded') or c.get('points_awarded') or 0) for c in checked)
        data.append(item)

    return Response(data)


@extend_schema(tags=['Exams'], summary='Delete exam', description='Owner or admin only.', responses={204: None})
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def exam_detail(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_owner(request, exam)
    exam.delete()
    return Response(status=204)


@extend_schema(
    tags=['Exams'], summary='Update exam settings',
    description='Owner or admin only. Updates bonus window, keywords, and group access list.',
    request=inline_serializer('ExamSettingsRequest', fields={
        'bonus_window_seconds': rf_serializers.IntegerField(),
        'keywords': rf_serializers.CharField(required=False),
        'allowed_group_ids': rf_serializers.ListField(child=rf_serializers.IntegerField(), required=False),
    }),
    responses={200: inline_serializer('ExamSettings', fields={
        'bonus_window_seconds': rf_serializers.IntegerField(),
        'keywords': rf_serializers.CharField(),
        'allowed_group_ids': rf_serializers.ListField(child=rf_serializers.IntegerField()),
    })},
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def exam_settings(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_owner(request, exam)

    try:
        bonus_window_seconds = int(request.data.get('bonus_window_seconds'))
    except (TypeError, ValueError):
        bonus_window_seconds = None
    if bonus_window_seconds is None or bonus_window_seconds < 1:
        return Response({'error': 'Bonus window must be at least 1 second.'}, status=400)

    keywords_raw = request.data.get('keywords') or ''
    keywords = ', '.join(k.strip() for k in keywords_raw.split(',') if k.strip())

    exam.bonus_window_seconds = bonus_window_seconds
    exam.keywords = keywords
    exam.save(update_fields=['bonus_window_seconds', 'keywords'])

    allowed_group_ids = request.data.get('allowed_group_ids')
    if isinstance(allowed_group_ids, list):
        exam.allowed_groups.set(Group.objects.filter(id__in=allowed_group_ids))

    return Response({
        'bonus_window_seconds': bonus_window_seconds,
        'keywords': keywords,
        'allowed_group_ids': list(exam.allowed_groups.values_list('id', flat=True)),
    })


@extend_schema(tags=['Exams'], summary='Export exam as CSV', responses={(200, 'text/csv'): OpenApiTypes.STR})
@api_view(['GET'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def exam_export(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_access(request, exam)
    csv_text = export_exam_to_csv(exam)
    filename = ''.join(c if c.isalnum() or c in '_-' else '_' for c in exam.name) + '.csv'
    response = HttpResponse(csv_text, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@extend_schema(
    tags=['Exams'], summary='Replace exam questions via CSV',
    description='Owner or admin only. Deletes all existing questions and imports the new CSV.',
    request=inline_serializer('CsvReplaceRequest', fields={'file': rf_serializers.FileField()}),
    responses={200: inline_serializer('ImportResult', fields={'question_count': rf_serializers.IntegerField()})},
)
@api_view(['PUT'])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def exam_import(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_owner(request, exam)
    upload = request.FILES.get('file')
    if not upload:
        return Response({'error': 'CSV file is required.'}, status=400)
    try:
        csv_text = upload.read().decode('utf-8')
        question_count = replace_exam_questions(exam, csv_text)
    except CsvImportError as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'question_count': question_count})


@extend_schema(
    tags=['Exams'], summary='List groups',
    description='Returns id and name for all groups. Used to populate the group selector when creating or editing an exam.',
    responses={200: inline_serializer('GroupOption', fields={
        'id': rf_serializers.IntegerField(),
        'name': rf_serializers.CharField(),
    }, many=True)},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def group_list(request):
    """Lightweight {id, name} list for the Create Exam / exam-settings group
    multiselect - any authenticated user can see group names to share an
    exam with, same as picking a name out of an address book."""
    return Response(list(Group.objects.order_by('name').values('id', 'name')))


# ---- Global settings ----

@extend_schema(
    methods=['GET'], tags=['Exams'], summary='Get app settings',
    responses={200: inline_serializer('AppSettingsResponse', fields={
        'sound_effects_enabled': rf_serializers.BooleanField(),
        'theme': rf_serializers.ChoiceField(choices=['dark', 'light']),
        'max_in_progress_instances': rf_serializers.IntegerField(),
    })},
)
@extend_schema(
    methods=['PUT'], tags=['Exams'], summary='Update app settings',
    description='Requires exams.change_appsettings permission. Must send all three fields.',
    request=inline_serializer('AppSettingsRequest', fields={
        'sound_effects_enabled': rf_serializers.BooleanField(),
        'theme': rf_serializers.ChoiceField(choices=['dark', 'light']),
        'max_in_progress_instances': rf_serializers.IntegerField(),
    }),
    responses={200: inline_serializer('AppSettingsResponse2', fields={
        'sound_effects_enabled': rf_serializers.BooleanField(),
        'theme': rf_serializers.ChoiceField(choices=['dark', 'light']),
        'max_in_progress_instances': rf_serializers.IntegerField(),
    })},
)
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


# ---- Editing exam content ----

def _load_question_detail(question):
    return {
        'id': question.id,
        'exam_id': question.exam_id,
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


class QuestionValidationError(Exception):
    pass


def _validate_question_payload(data):
    question_text = (data.get('question_text') or '').strip()
    if not question_text:
        raise QuestionValidationError('Question text is required.')

    question_type = Question.MULTI if data.get('question_type') == 'multi' else Question.SINGLE
    raw_options = data.get('options') if isinstance(data.get('options'), list) else []
    options = [
        {'text': (o.get('text') or '').strip(), 'is_correct': bool(o.get('is_correct'))}
        for o in raw_options
    ]
    options = [o for o in options if o['text']]

    if len(options) < 2:
        raise QuestionValidationError('At least 2 options are required.')
    correct_count = sum(1 for o in options if o['is_correct'])
    if correct_count == 0:
        raise QuestionValidationError('At least one option must be marked correct.')
    if question_type == Question.SINGLE and correct_count > 1:
        raise QuestionValidationError('Single choice questions can only have one correct option.')

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


@extend_schema(
    methods=['GET'], tags=['Exams'], summary='Get exam questions',
    description='Returns all questions and options for an exam, plus edit capability flag. '
                'Used to load the question editor and the exam-start setup panel.',
    responses={200: OpenApiTypes.OBJECT},
)
@extend_schema(
    methods=['POST'], tags=['Exams'], summary='Add question to exam',
    description='Owner or admin only. Appends a new question with options.',
    request=inline_serializer('QuestionPayload', fields={
        'question_text': rf_serializers.CharField(),
        'question_type': rf_serializers.ChoiceField(choices=['single', 'multi']),
        'points': rf_serializers.IntegerField(required=False),
        'image_link': rf_serializers.URLField(required=False, allow_blank=True),
        'explanation': rf_serializers.CharField(required=False, allow_blank=True),
        'options': rf_serializers.ListField(child=rf_serializers.DictField()),
    }),
    responses={201: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def exam_questions(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)

    if request.method == 'GET':
        _require_exam_access(request, exam)
        questions = [_load_question_detail(q) for q in exam.questions.order_by('sort_order')]
        return Response({
            'exam_id': exam.id,
            'exam_name': exam.name,
            'bonus_window_seconds': exam.bonus_window_seconds,
            'keywords': exam.keywords,
            'allowed_group_ids': list(exam.allowed_groups.values_list('id', flat=True)),
            'can_edit': _can_edit_exam(request.user, exam),
            'questions': questions,
        })

    _require_exam_owner(request, exam)
    try:
        payload = _validate_question_payload(request.data)
    except QuestionValidationError as exc:
        return Response({'error': str(exc)}, status=400)

    with transaction.atomic():
        max_sort = exam.questions.aggregate(m=Max('sort_order'))['m']
        question = Question.objects.create(
            exam=exam,
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


@extend_schema(
    methods=['PUT'], tags=['Exams'], summary='Update question',
    description='Owner or admin only. Replaces all options.',
    request=inline_serializer('QuestionUpdatePayload', fields={
        'question_text': rf_serializers.CharField(),
        'question_type': rf_serializers.ChoiceField(choices=['single', 'multi']),
        'points': rf_serializers.IntegerField(required=False),
        'image_link': rf_serializers.URLField(required=False, allow_blank=True),
        'explanation': rf_serializers.CharField(required=False, allow_blank=True),
        'options': rf_serializers.ListField(child=rf_serializers.DictField()),
    }),
    responses={200: OpenApiTypes.OBJECT},
)
@extend_schema(methods=['DELETE'], tags=['Exams'], summary='Delete question', responses={204: None})
@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def question_detail(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    _require_exam_owner(request, question.exam)

    if request.method == 'DELETE':
        question.delete()
        return Response(status=204)

    try:
        payload = _validate_question_payload(request.data)
    except QuestionValidationError as exc:
        return Response({'error': str(exc)}, status=400)

    with transaction.atomic():
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

    has_existing_instance = InProgressAttempt.objects.filter(exam=exam, user=request.user).exists()
    if not has_existing_instance:
        max_instances = AppSettings.get_solo().max_in_progress_instances
        if max_instances > 0:
            instance_count = InProgressAttempt.objects.filter(user=request.user).count()
            if instance_count >= max_instances:
                return Response({
                    'error': (
                        f"You've reached the maximum of {max_instances} in-progress exam instance(s). "
                        'Finish or delete an existing instance before starting a new one.'
                    ),
                }, status=400)

    all_questions = list(exam.questions.order_by('sort_order'))

    requested_ids = request.data.get('question_ids')
    if isinstance(requested_ids, list):
        requested_ids = {int(i) for i in requested_ids}
        selected = random.sample(qs := [q for q in all_questions if q.id in requested_ids], len(qs))
        if not selected:
            return Response({'error': 'None of the requested questions exist in this exam.'}, status=400)
    else:
        count = request.data.get('count')
        if count in (None, 'all'):
            selected = random.sample(all_questions, len(all_questions))
        else:
            try:
                count = int(count)
            except (TypeError, ValueError):
                count = len(all_questions)
            count = max(1, min(count or len(all_questions), len(all_questions)))
            selected = random.sample(all_questions, count)

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
            'select_count': select_count,
            'options': [{'id': o.id, 'text': o.option_text} for o in options],
        })

    return Response({
        'exam_id': exam.id,
        'exam_name': exam.name,
        'bonus_window_seconds': exam.bonus_window_seconds,
        'questions': questions,
    })


# ---- Resumable in-progress exam state ----

@extend_schema(exclude=True)
@api_view(['PUT', 'GET', 'DELETE'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def exam_progress(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
    _require_exam_access(request, exam)

    if request.method == 'DELETE':
        InProgressAttempt.objects.filter(exam=exam, user=request.user).delete()
        return Response(status=204)

    if request.method == 'GET':
        row = InProgressAttempt.objects.filter(exam=exam, user=request.user).first()
        if not row:
            return Response({'error': 'No saved progress for this exam.'}, status=404)
        return Response({
            'exam_id': row.exam_id,
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

    elapsed_seconds = request.data.get('elapsed_seconds')
    started_at = request.data.get('started_at') or datetime.now(dt_timezone.utc).isoformat()
    if isinstance(started_at, str):
        started_at = parse_datetime(started_at) or datetime.now(dt_timezone.utc)

    InProgressAttempt.objects.update_or_create(
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


# Instant per-question feedback while taking an exam (not recorded in attempt history).
@extend_schema(exclude=True)
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def question_check(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    _require_exam_access(request, question.exam)
    options = list(question.options.all())
    correct_ids = {o.id for o in options if o.is_correct}
    selected_ids = request.data.get('selected_option_ids')
    selected_ids = {int(i) for i in selected_ids} if isinstance(selected_ids, list) else set()

    is_correct = correct_ids == selected_ids
    return Response({
        'is_correct': is_correct,
        'correct_option_ids': list(correct_ids),
        'explanation': question.explanation,
    })


@extend_schema(exclude=True)
@api_view(['POST'])
@authentication_classes([CsrfExemptSessionAuthentication])
@permission_classes([IsAuthenticated, NoTokenAuthOnGameplay])
def exam_submit(request, exam_id):
    exam = get_object_or_404(Exam, id=exam_id)
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
        question = Question.objects.filter(id=answer.get('question_id'), exam=exam).first()
        if not question:
            continue
        options = list(question.options.order_by('sort_order'))
        correct_ids = {o.id for o in options if o.is_correct}
        selected_ids_raw = answer.get('selected_option_ids')
        selected_ids = [int(i) for i in selected_ids_raw] if isinstance(selected_ids_raw, list) else []

        is_correct = correct_ids == set(selected_ids)
        if is_correct:
            num_correct += 1
        total_points += question.points

        try:
            client_awarded = round(float(answer.get('points_awarded')))
            points_awarded = max(0, client_awarded)
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

    with transaction.atomic():
        attempt = Attempt.objects.create(
            exam=exam,
            user=request.user,
            started_at=started_at,
            num_questions=len(answers),
            num_correct=num_correct,
            total_points=total_points,
            points_earned=points_earned,
        )
        AttemptAnswer.objects.bulk_create([
            AttemptAnswer(
                attempt=attempt,
                question_id=r['question_id'],
                selected_option_ids=r['selected_option_ids'],
                is_correct=r['is_correct'],
                points_awarded=r['points_awarded'],
            )
            for r in results
        ])

    return Response({
        'attempt_id': attempt.id,
        'exam_id': exam.id,
        'exam_name': exam.name,
        'num_questions': len(answers),
        'num_correct': num_correct,
        'total_points': total_points,
        'points_earned': points_earned,
        'results': results,
    })


# ---- Attempt history ----

@extend_schema(
    tags=['Exams'], summary='List attempts for an exam',
    description='Returns all attempts for the current user. Users with exams.view_attempt see all users\' attempts.',
    responses={200: inline_serializer('AttemptSummary', fields={
        'id': rf_serializers.IntegerField(),
        'started_at': rf_serializers.DateTimeField(),
        'finished_at': rf_serializers.DateTimeField(),
        'num_questions': rf_serializers.IntegerField(),
        'num_correct': rf_serializers.IntegerField(),
        'total_points': rf_serializers.IntegerField(),
        'points_earned': rf_serializers.IntegerField(),
    }, many=True)},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def exam_attempts(request, exam_id):
    qs = Attempt.objects.filter(exam_id=exam_id)
    if not request.user.has_perm('exams.view_attempt'):
        qs = qs.filter(user=request.user)
    attempts = qs.order_by('-finished_at').values(
        'id', 'started_at', 'finished_at', 'num_questions', 'num_correct', 'total_points', 'points_earned'
    )
    return Response(list(attempts))


@extend_schema(
    tags=['Exams'], summary='Get attempt detail with per-question results',
    description='Returns full attempt with per-question correctness, selected options, and explanations. '
                'Own attempts only unless the user has exams.view_attempt.',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def attempt_detail(request, attempt_id):
    attempt = get_object_or_404(Attempt, id=attempt_id)
    if attempt.user_id != request.user.id and not request.user.has_perm('exams.view_attempt'):
        raise exceptions.PermissionDenied('Missing permission: exams.view_attempt')

    results = []
    for a in attempt.answers.all():
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
        'id': attempt.id,
        'exam_id': attempt.exam_id,
        'started_at': attempt.started_at,
        'finished_at': attempt.finished_at,
        'num_questions': attempt.num_questions,
        'num_correct': attempt.num_correct,
        'total_points': attempt.total_points,
        'points_earned': attempt.points_earned,
        'results': results,
    })
