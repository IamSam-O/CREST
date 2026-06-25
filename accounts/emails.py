from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import EmailSettings


def send_invite_email(invite, request):
    """Shared by accounts/admin.py's InviteAdmin and adminui's InviteViewSet so
    the two invite-creation paths (Django admin, custom admin UI) send the
    exact same email instead of maintaining the template logic twice."""
    accept_url = request.build_absolute_uri(f'/accounts/invite/{invite.token}/')
    email_settings = EmailSettings.get_solo()
    context = {'invite': invite, 'accept_url': accept_url}

    message = EmailMultiAlternatives(
        subject='You have been invited to CREST',
        body=render_to_string('accounts/email/invite.txt', context),
        from_email=email_settings.default_from_email or None,
        to=[invite.email],
        connection=email_settings.get_connection(),
    )
    message.attach_alternative(render_to_string('accounts/email/invite.html', context), 'text/html')
    message.send(fail_silently=False)
