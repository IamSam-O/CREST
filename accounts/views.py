from django.contrib.auth import login
from django.contrib.auth.views import PasswordChangeView as BasePasswordChangeView
from django.core.mail import EmailMessage
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import FormView
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as rf_serializers
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes

from .authentication import CsrfExemptSessionAuthentication
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .forms import InviteAcceptForm, ThemedPasswordChangeForm
from .models import EmailSettings, Invite


class PasswordChangeView(BasePasswordChangeView):
    """Same as Django's built-in PasswordChangeView, but also clears the
    forced-change gate enforced by RequirePasswordChangeMiddleware."""

    success_url = reverse_lazy('password_change_done')
    form_class = ThemedPasswordChangeForm

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.user.must_change_password = False
        self.request.user.save(update_fields=['must_change_password'])
        return response


class InviteAcceptView(FormView):
    template_name = 'accounts/invite_accept.html'
    form_class = InviteAcceptForm

    def dispatch(self, request, *args, **kwargs):
        self.invite = get_object_or_404(Invite, token=kwargs['token'])
        if not self.invite.is_usable():
            return render(request, 'accounts/invite_invalid.html', {'invite': self.invite}, status=400)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        from django.utils import timezone

        user = form.save()
        if self.invite.group:
            user.groups.add(self.invite.group)
        user.email = self.invite.email
        user.save(update_fields=['email'])
        self.invite.accepted_at = timezone.now()
        self.invite.save(update_fields=['accepted_at'])
        login(self.request, user)
        return render(self.request, 'accounts/invite_accepted.html', {'user': user})


@extend_schema(
    tags=['Account'], summary='Get or rotate personal API token',
    description='GET returns the current token (creates one if none exists). POST replaces it. '
                'Use the token in the Authorization header: `Token <value>`.',
    request=None,
    responses={200: inline_serializer('TokenResponse', fields={'token': rf_serializers.CharField()})},
)
@api_view(['GET', 'POST'])
@authentication_classes([CsrfExemptSessionAuthentication, TokenAuthentication])
@permission_classes([IsAuthenticated])
def my_token(request):
    """Self-service personal API token, available to every authenticated
    user (not just staff/admins) from /manage/'s My Account section - anyone
    can call the API, but every endpoint still enforces the same
    ownership/permission rules as the browser UI."""
    if request.method == 'POST':
        Token.objects.filter(user=request.user).delete()
        token = Token.objects.create(user=request.user)
    else:
        token, _created = Token.objects.get_or_create(user=request.user)
    return Response({'token': token.key})


def _test_connection(email_settings):
    connection = email_settings.get_connection()
    try:
        connection.open()
        connection.close()
    except Exception as exc:
        return False, str(exc)
    return True, None


@extend_schema(
    tags=['Account'], summary='Verify SMTP connection',
    description='Checks the saved email settings can open a connection without sending anything. Admin only.',
    request=None,
    responses={
        200: inline_serializer('SmtpSuccess', fields={'success': rf_serializers.BooleanField()}),
        400: inline_serializer('SmtpFailure', fields={'success': rf_serializers.BooleanField(), 'error': rf_serializers.CharField()}),
    },
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def test_email_connection(request):
    """Verifies the currently saved SMTP settings actually work, without
    sending a real invite. Reports the specific failure reason (auth,
    connection, TLS handshake) rather than a generic error. Used for API
    parity; the same check also runs from the admin-only settings page."""
    success, error = _test_connection(EmailSettings.get_solo())
    if not success:
        return Response({'success': False, 'error': error}, status=400)
    return Response({'success': True})


@extend_schema(
    tags=['Account'], summary='Send a test email',
    description='Sends a test message to a given address using the saved SMTP settings. Admin only.',
    request=inline_serializer('SendEmailRequest', fields={'to': rf_serializers.EmailField()}),
    responses={
        200: inline_serializer('SendEmailSuccess', fields={'success': rf_serializers.BooleanField()}),
        400: inline_serializer('SendEmailError', fields={'error': rf_serializers.CharField()}),
    },
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def send_test_email(request):
    to_email = request.data.get('to', '').strip()
    if not to_email:
        return Response({'error': 'Recipient email is required.'}, status=400)
    settings_row = EmailSettings.get_solo()
    try:
        message = EmailMessage(
            subject='CREST test email',
            body="This is a test email from your CREST app's SMTP settings. If you received this, sending works.",
            from_email=settings_row.default_from_email or None,
            to=[to_email],
            connection=settings_row.get_connection(),
        )
        message.send(fail_silently=False)
    except Exception as exc:
        return Response({'error': str(exc)}, status=400)
    return Response({'success': True})
