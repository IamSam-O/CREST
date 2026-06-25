import random
import secrets
import string

from django.conf import settings
from django.db import models

from exams.models import Exam


def _generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _generate_passcode():
    return ''.join(random.choices(string.digits, k=6))


class MultiplayerSession(models.Model):
    LOBBY = 'lobby'
    ACTIVE = 'active'
    PAUSED = 'paused'
    FINISHED = 'finished'
    ABANDONED = 'abandoned'
    STATUS_CHOICES = [
        (LOBBY, 'lobby'), (ACTIVE, 'active'), (PAUSED, 'paused'), (FINISHED, 'finished'), (ABANDONED, 'abandoned'),
    ]

    room_code = models.CharField(max_length=12, unique=True, default=_generate_room_code)
    passcode = models.CharField(max_length=12, default=_generate_passcode)
    # Hosting needs no login (matches the "no login for multiplayer" intent
    # for guests too) - this secret, known only to whoever created the
    # session via the host control URL, is what authorizes host actions
    # over the websocket instead of a logged-in user match.
    host_secret = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='multiplayer_sessions')
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='hosted_sessions'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=LOBBY)
    # Shuffled question/option snapshot taken when the host starts the round -
    # reuses the same "JSON blob over normalized child table" pattern the
    # app already uses for in_progress_attempts, rather than a new table.
    questions_json = models.JSONField(default=list)
    current_index = models.IntegerField(default=0)
    time_limit_seconds = models.IntegerField(default=0)  # 0 = no limit
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.room_code} ({self.exam.name})'


class MultiplayerParticipant(models.Model):
    session = models.ForeignKey(MultiplayerSession, on_delete=models.CASCADE, related_name='participants')
    client_id = models.CharField(max_length=64)
    display_name = models.CharField(max_length=64)
    score = models.IntegerField(default=0)
    answers_json = models.JSONField(default=dict)
    connected = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['session', 'client_id'], name='uniq_session_client'),
        ]

    def __str__(self):
        return self.display_name
