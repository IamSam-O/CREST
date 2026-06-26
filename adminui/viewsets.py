import csv
import io

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.db.models import Count, F
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from accounts.emails import send_invite_email
from accounts.models import EmailSettings, Invite, User
from exams.csv_io import HEADER, OPTION_COLUMNS
from exams.models import AppSettings, Exam, ExamInstance, GradeScale, Option, Question, QuestionBank
from multiplayer.models import MultiplayerParticipant, MultiplayerSession

from .serializers import (
    AppSettingsSerializer,
    EmailSettingsSerializer,
    ExamInstanceSerializer,
    GradeScaleSerializer,
    GroupSerializer,
    InviteSerializer,
    MultiplayerParticipantSerializer,
    MultiplayerSessionSerializer,
    QuestionBankSerializer,
    UserSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]


MEANINGFUL_PERMISSION_CODENAMES = ['add_exam', 'view_exam', 'view_examinstance', 'change_appsettings']


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.prefetch_related('permissions').order_by('name')
    serializer_class = GroupSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(tags=['Admin'], summary='List meaningful permissions', responses={200: OpenApiTypes.OBJECT})
    @action(detail=False)
    def permissions_catalog(self, request):
        perms = (
            Permission.objects.filter(content_type__app_label='exams', codename__in=MEANINGFUL_PERMISSION_CODENAMES)
            .annotate(app_label=F('content_type__app_label'))
            .order_by('codename')
            .values('id', 'name', 'codename', 'app_label')
        )
        return Response(list(perms))


class InviteViewSet(viewsets.ModelViewSet):
    queryset = Invite.objects.select_related('group', 'invited_by').order_by('-created_at')
    serializer_class = InviteSerializer
    permission_classes = [IsAdminUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invite = serializer.save(invited_by=request.user)
        try:
            send_invite_email(invite, request)
        except Exception as exc:
            return Response({'error': f'Invite was created, but the email failed to send: {exc}'}, status=400)
        return Response(serializer.data, status=201)


@extend_schema(tags=['Admin'], summary='List exams (id + name only)', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAdminUser])
def exam_options_view(request):
    return Response(list(Exam.objects.order_by('name').values('id', 'name')))


@extend_schema(tags=['Admin'], summary='List banks (id + name only)', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAdminUser])
def bank_options_view(request):
    return Response(list(QuestionBank.objects.order_by('name').values('id', 'name')))


class QuestionBankViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = QuestionBankSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return QuestionBank.objects.annotate(question_count=Count('questions')).order_by('-created_at')


class ExamInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ExamInstanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ExamInstance.objects.select_related('exam', 'user').order_by('-finished_at')
        if user.is_staff:
            return qs
        if user.has_perm('exams.add_exam'):
            return qs.filter(exam__owner=user)
        return qs.none()

    @action(detail=True, methods=['get'])
    def drill(self, request, pk=None):
        instance = self.get_object()
        answers = (
            instance.answers
            .select_related('question')
            .prefetch_related('question__options')
            .order_by('question__sort_order')
        )
        results = []
        for aa in answers:
            q = aa.question
            opts = list(q.options.order_by('sort_order'))
            results.append({
                'questionId': q.id,
                'questionText': q.question_text,
                'questionType': q.question_type,
                'isCorrect': aa.is_correct,
                'pointsAwarded': aa.points_awarded,
                'points': q.points,
                'selectedOptionIds': aa.selected_option_ids,
                'explanation': q.explanation,
                'options': [{'id': o.id, 'text': o.option_text, 'isCorrect': o.is_correct} for o in opts],
            })
        pct = round(instance.num_correct / instance.num_questions * 100) if instance.num_questions else 0
        base_earned = sum(r['points'] for r in results if r['isCorrect'])
        return Response({
            'id': instance.id,
            'examName': instance.exam.name,
            'user': instance.user.username,
            'finishedAt': instance.finished_at,
            'numQuestions': instance.num_questions,
            'numCorrect': instance.num_correct,
            'totalPoints': instance.total_points,
            'pointsEarned': instance.points_earned,
            'basePointsEarned': base_earned,
            'bonusPointsEarned': max(0, instance.points_earned - base_earned),
            'percentCorrect': pct,
            'grade': instance.grade,
            'gradeScaleId': instance.grade_scale_id,
            'gradeLog': instance.grade_log,
            'results': results,
        })

    @action(detail=True, methods=['post'], url_path='re-evaluate')
    def re_evaluate(self, request, pk=None):
        instance = self.get_object()
        note = (request.data.get('note') or '').strip()
        if not note:
            return Response({'error': 'A note is required explaining the change.'}, status=400)

        grade = None
        scale_name = None
        grade_scale_id = request.data.get('grade_scale_id')
        if grade_scale_id:
            scale = GradeScale.objects.filter(id=grade_scale_id).first()
            if not scale:
                return Response({'error': 'Grade scale not found.'}, status=404)
            pct = round(instance.num_correct / instance.num_questions * 100) if instance.num_questions else 0
            grade = scale.compute_grade(pct) or 'N/A'
            scale_name = scale.name

        instance.grade_log = (instance.grade_log or []) + [{
            'changed_at': timezone.now().isoformat(),
            'changed_by': request.user.username,
            'scale_name': scale_name,
            'previous_grade': instance.grade,
            'new_grade': grade,
            'note': note,
        }]
        instance.grade = grade
        instance.grade_scale_id = grade_scale_id if grade_scale_id else None
        instance.save(update_fields=['grade', 'grade_scale_id', 'grade_log'])
        return Response({'grade': instance.grade, 'grade_log': instance.grade_log})

    @action(detail=True, methods=['get'], url_path='missed-csv')
    def missed_csv(self, request, pk=None):
        instance = self.get_object()
        wrong = (
            instance.answers
            .filter(is_correct=False)
            .select_related('question')
            .prefetch_related('question__options')
            .order_by('question__sort_order')
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(HEADER)
        for aa in wrong:
            q = aa.question
            opts = list(q.options.order_by('sort_order'))
            correct_indexes = ','.join(str(i + 1) for i, o in enumerate(opts) if o.is_correct)
            option_cells = [opts[i].option_text if i < len(opts) else '' for i in range(len(OPTION_COLUMNS))]
            writer.writerow([
                q.question_text,
                'Checkbox' if q.question_type == Question.MULTI else 'Multiple Choice',
                q.category,
                *option_cells,
                correct_indexes,
                q.points,
                q.image_link or '',
                q.explanation or '',
            ])
        safe_name = ''.join(c if c.isalnum() or c in '_-' else '_' for c in instance.exam.name)
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="missed_{safe_name}_{instance.id}.csv"'
        return response

    @action(detail=True, methods=['post'], url_path='generate-exam')
    def generate_exam(self, request, pk=None):
        instance = self.get_object()
        wrong = (
            instance.answers
            .filter(is_correct=False)
            .select_related('question')
            .prefetch_related('question__options')
            .order_by('question__sort_order')
        )
        if not wrong.exists():
            return Response({'error': 'No missed questions to generate an exam from.'}, status=400)

        base_name = request.data.get('name') or f'Missed Questions – {instance.exam.name}'
        name = base_name
        suffix = 2
        while QuestionBank.objects.filter(name__iexact=name).exists():
            name = f'{base_name} ({suffix})'
            suffix += 1

        with transaction.atomic():
            bank = QuestionBank.objects.create(name=name, owner=request.user)
            for idx, aa in enumerate(wrong):
                q = aa.question
                new_q = Question.objects.create(
                    bank=bank,
                    category=q.category,
                    question_text=q.question_text,
                    question_type=q.question_type,
                    points=q.points,
                    image_link=q.image_link,
                    explanation=q.explanation,
                    sort_order=idx,
                )
                Option.objects.bulk_create([
                    Option(question=new_q, option_text=o.option_text, is_correct=o.is_correct, sort_order=o.sort_order)
                    for o in q.options.order_by('sort_order')
                ])

            question_count = wrong.count()
            exam_name = name
            while Exam.objects.filter(name__iexact=exam_name).exists():
                exam_name = f'{name} (exam)'
            exam = Exam.objects.create(
                name=exam_name,
                question_bank=bank,
                question_count=question_count,
                owner=request.user,
            )

        return Response({'bankId': bank.id, 'examId': exam.id, 'examName': exam.name, 'questionCount': question_count}, status=201)


class GradeScaleViewSet(viewsets.ModelViewSet):
    queryset = GradeScale.objects.order_by('name')
    serializer_class = GradeScaleSerializer
    permission_classes = [IsAdminUser]


class MultiplayerSessionViewSet(viewsets.ModelViewSet):
    queryset = MultiplayerSession.objects.select_related('exam', 'host').order_by('-created_at')
    serializer_class = MultiplayerSessionSerializer
    permission_classes = [IsAdminUser]


class MultiplayerParticipantViewSet(viewsets.ModelViewSet):
    serializer_class = MultiplayerParticipantSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = MultiplayerParticipant.objects.order_by('-joined_at')
        session_id = self.request.query_params.get('session')
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs


@extend_schema(
    tags=['Admin'], summary='Get or update app settings',
    request=AppSettingsSerializer, responses={200: AppSettingsSerializer},
)
@api_view(['GET', 'PUT'])
@permission_classes([IsAdminUser])
def app_settings_view(request):
    instance = AppSettings.get_solo()
    if request.method == 'PUT':
        serializer = AppSettingsSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    return Response(AppSettingsSerializer(instance).data)


@extend_schema(
    tags=['Admin'], summary='Get or update SMTP email settings',
    request=EmailSettingsSerializer, responses={200: EmailSettingsSerializer},
)
@api_view(['GET', 'PUT'])
@permission_classes([IsAdminUser])
def email_settings_view(request):
    instance = EmailSettings.get_solo()
    if request.method == 'PUT':
        serializer = EmailSettingsSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(EmailSettingsSerializer(instance).data)
    return Response(EmailSettingsSerializer(instance).data)


@extend_schema(tags=['Admin'], summary='Current user roles and capabilities', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def whoami_view(request):
    return Response({
        'isStaff': request.user.is_staff,
        'canCreateExam': request.user.has_perm('exams.add_exam'),
    })
