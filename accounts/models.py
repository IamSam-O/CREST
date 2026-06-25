import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils import timezone

from .crypto import decrypt, encrypt


class EncryptedCharField(models.CharField):
    """Transparently encrypts on write / decrypts on read, keyed by
    SECRET_KEY (see crypto.py) rather than stored alongside the ciphertext -
    a hash can't be used here since the plaintext must be recoverable to
    actually authenticate with it later."""

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return decrypt(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return encrypt(value)


class User(AbstractUser):
    # username stays Django's default login identifier; email is only used
    # for invites/notifications, not authentication.
    email = models.EmailField(unique=True, blank=True, null=True)
    must_change_password = models.BooleanField(default=False)


class EmailSettings(models.Model):
    """Singleton row (manual get_or_create(pk=1)) holding SMTP credentials,
    editable from an admin-only page instead of env vars so they can be
    changed without a container rebuild. The password is encrypted at rest
    (EncryptedCharField, keyed by SECRET_KEY) rather than stored as plain
    text in the SQLite file."""

    id = models.PositiveIntegerField(primary_key=True, default=1)
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    username = models.CharField(max_length=255, blank=True)
    password = EncryptedCharField(max_length=500, blank=True)
    default_from_email = models.EmailField(blank=True)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def get_connection(self):
        from django.core.mail import get_connection

        return get_connection(
            host=self.host,
            port=self.port,
            username=self.username or None,
            password=self.password or None,
            use_tls=self.use_tls,
            use_ssl=self.use_ssl,
        )



def _default_expiry():
    return timezone.now() + timedelta(days=7)


class Invite(models.Model):
    email = models.EmailField()
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_invites')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_usable(self):
        return self.accepted_at is None and not self.is_expired()

    def __str__(self):
        return f'Invite for {self.email}'
