from django.contrib.auth.models import Group, Permission
from django.db.models import F
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as rf_serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from accounts.emails import send_invite_email
from accounts.models import EmailSettings, Invite, User
from exams.models import AppSettings, Attempt, Exam
from multiplayer.models import MultiplayerParticipant, MultiplayerSession

from .serializers import (
    AppSettingsSerializer,
    AttemptSerializer,
    EmailSettingsSerializer,
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

    @extend_schema(
        tags=['Admin'], summary='List meaningful permissions',
        description='Returns only the permission codenames that actually gate features in this app.',
        responses={200: inline_serializer('PermissionOption', fields={
            'id': rf_serializers.IntegerField(),
            'name': rf_serializers.CharField(),
            'codename': rf_serializers.CharField(),
            'app_label': rf_serializers.CharField(),
        }, many=True)},
    )
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


# Read-only - exam content/ownership is managed from the Library now, not
# Manage; this just backs the Exam column/select in Attempts and Multiplayer
# Sessions (which are still staff-level, not admin-only).
@extend_schema(
    tags=['Admin'], summary='List exams (id + name only)',
    description='Lightweight list for populating select dropdowns in the Attempts and Multiplayer Sessions tables.',
    responses={200: inline_serializer('ExamOptionAdmin', fields={
        'id': rf_serializers.IntegerField(),
        'name': rf_serializers.CharField(),
    }, many=True)},
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def exam_options_view(request):
    return Response(list(Exam.objects.order_by('name').values('id', 'name')))


class AttemptViewSet(viewsets.ModelViewSet):
    queryset = Attempt.objects.select_related('exam', 'user').order_by('-finished_at')
    serializer_class = AttemptSerializer
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
@extend_schema(
    tags=['Admin'], summary='Current user roles and capabilities',
    description='Used by the app to decide which sidebar sections and UI controls to show.',
    responses={200: inline_serializer('WhoamiResponse', fields={
        'is_staff': rf_serializers.BooleanField(),
        'can_create_exam': rf_serializers.BooleanField(),
    })},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def whoami_view(request):
    return Response({
        'isStaff': request.user.is_staff,
        'canCreateExam': request.user.has_perm('exams.add_exam'),
    })
