import csv
import io

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.db.models import F
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
from exams.models import AppSettings, Attempt, Exam, GradeScale, Option, Question
from multiplayer.models import MultiplayerParticipant, MultiplayerSession

from .serializers import (
    AppSettingsSerializer,
    AttemptSerializer,
    EmailSettingsSerializer,
    GradeScaleSerializer,
    GroupSerializer,
    InviteSerializer,
    MultiplayerParticipantSerializer,
    MultiplayerSessionSerializer,
    UserSerializer,
)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]


# The only permission codenames actually checked anywhere via has_perm() (see
# exams/views.py's _require_perm calls) - everything else in Django's
# auto-generated table (a separate add/change/delete/view permission per
# model, across every app) is noise that doesn't gate anything. Notably,
# Question/Option editing has no entry here: it's ownership-based now (see
# _require_exam_owner), not permission-based, so there's no separate
# "edit question" permission distinct from "edit exam" - editing an exam
# you own covers its questions and options too.
MEANINGFUL_PERMISSION_CODENAMES = ['add_exam', 'view_exam', 'view_attempt', 'change_appsettings']


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
            # The invite row is already saved (matches accounts/admin.py's InviteAdmin
            # behavior) - surface a readable {'error': ...} response, the same shape
            # every other endpoint in this app uses, instead of an opaque 500.
            return Response({'error': f'Invite was created, but the email failed to send: {exc}'}, status=400)
        return Response(serializer.data, status=201)


@extend_schema(tags=['Admin'], summary='List exams (id + name only)', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAdminUser])
def exam_options_view(request):
    return Response(list(Exam.objects.order_by('name').values('id', 'name')))


class AttemptViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AttemptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Attempt.objects.select_related('exam', 'user').order_by('-finished_at')
        if user.is_staff:
            return qs
        if user.has_perm('exams.add_exam'):
            return qs.filter(exam__owner=user)
        return qs.none()

    @action(detail=True, methods=['get'])
    def drill(self, request, pk=None):
        attempt = self.get_object()
        answers = (
            attempt.answers
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
        pct = round(attempt.num_correct / attempt.num_questions * 100) if attempt.num_questions else 0
        base_earned = sum(r['points'] for r in results if r['isCorrect'])
        return Response({
            'id': attempt.id,
            'examName': attempt.exam.name,
            'user': attempt.user.username,
            'finishedAt': attempt.finished_at,
            'numQuestions': attempt.num_questions,
            'numCorrect': attempt.num_correct,
            'totalPoints': attempt.total_points,
            'pointsEarned': attempt.points_earned,
            'basePointsEarned': base_earned,
            'bonusPointsEarned': max(0, attempt.points_earned - base_earned),
            'percentCorrect': pct,
            'grade': attempt.grade,
            'gradeScaleId': attempt.grade_scale_id,
            'gradeLog': attempt.grade_log,
            'results': results,
        })

    @action(detail=True, methods=['post'], url_path='re-evaluate')
    def re_evaluate(self, request, pk=None):
        attempt = self.get_object()
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
            pct = round(attempt.num_correct / attempt.num_questions * 100) if attempt.num_questions else 0
            grade = scale.compute_grade(pct) or 'N/A'
            scale_name = scale.name

        attempt.grade_log = (attempt.grade_log or []) + [{
            'changed_at': timezone.now().isoformat(),
            'changed_by': request.user.username,
            'scale_name': scale_name,
            'previous_grade': attempt.grade,
            'new_grade': grade,
            'note': note,
        }]
        attempt.grade = grade
        attempt.grade_scale_id = int(grade_scale_id) if grade_scale_id else None
        attempt.save(update_fields=['grade', 'grade_scale_id', 'grade_log'])
        return Response({'grade': attempt.grade, 'grade_log': attempt.grade_log})

    @action(detail=True, methods=['get'], url_path='missed-csv')
    def missed_csv(self, request, pk=None):
        attempt = self.get_object()
        wrong = (
            attempt.answers
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
                *option_cells,
                correct_indexes,
                q.points,
                q.image_link or '',
                q.explanation or '',
            ])
        safe_name = ''.join(c if c.isalnum() or c in '_-' else '_' for c in attempt.exam.name)
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="missed_{safe_name}_{attempt.id}.csv"'
        return response

    @action(detail=True, methods=['post'], url_path='generate-exam')
    def generate_exam(self, request, pk=None):
        attempt = self.get_object()
        wrong = (
            attempt.answers
            .filter(is_correct=False)
            .select_related('question')
            .prefetch_related('question__options')
            .order_by('question__sort_order')
        )
        if not wrong.exists():
            return Response({'error': 'No missed questions to generate an exam from.'}, status=400)

        base_name = request.data.get('name') or f'Missed Questions – {attempt.exam.name}'
        name = base_name
        suffix = 2
        while Exam.objects.filter(name__iexact=name).exists():
            name = f'{base_name} ({suffix})'
            suffix += 1

        with transaction.atomic():
            exam = Exam.objects.create(name=name, owner=request.user)
            for idx, aa in enumerate(wrong):
                q = aa.question
                new_q = Question.objects.create(
                    exam=exam,
                    question_text=q.question_text,
                    question_type=q.question_type,
                    points=q.points,
                    image_link=q.image_link,
                    explanation=q.explanation,
                    sort_order=idx,
                )
                Option.objects.bulk_create([
                    Option(
                        question=new_q,
                        option_text=o.option_text,
                        is_correct=o.is_correct,
                        sort_order=o.sort_order,
                    )
                    for o in q.options.order_by('sort_order')
                ])

        return Response({'examId': exam.id, 'examName': exam.name, 'questionCount': idx + 1}, status=201)


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


# Singleton row - same get_solo() pattern as exams/views.py:app_settings,
# exposed as plain GET/PUT instead of router CRUD since there's only ever one row.
@extend_schema(
    tags=['Admin'], summary='Get or update app settings',
    description='GET returns the current singleton settings row. PUT replaces it. Requires is_staff.',
    request=AppSettingsSerializer,
    responses={200: AppSettingsSerializer},
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
    description='GET returns the singleton row (password field is write-only). PUT replaces it. Admin only.',
    request=EmailSettingsSerializer,
    responses={200: EmailSettingsSerializer},
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


# Lets the Manage UI show/hide the staff-level and admin-level sidebar groups -
# /manage/ itself is login_required (everyone needs it for My Account/API Token),
# but most sections are still gated server-side by IsAdminUser/IsManageAdmin above.
@extend_schema(tags=['Admin'], summary='Current user roles and capabilities', responses={200: OpenApiTypes.OBJECT})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def whoami_view(request):
    return Response({
        'isStaff': request.user.is_staff,
        'canCreateExam': request.user.has_perm('exams.add_exam'),
    })
