import django.db.models.deletion
import multiplayer.models
import secrets
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('exams', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MultiplayerSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_code', models.CharField(default=multiplayer.models._generate_room_code, max_length=12, unique=True)),
                ('passcode', models.CharField(default=multiplayer.models._generate_passcode, max_length=12)),
                ('host_secret', models.CharField(default=secrets.token_urlsafe, max_length=64, unique=True)),
                ('status', models.CharField(
                    choices=[('lobby', 'lobby'), ('active', 'active'), ('paused', 'paused')],
                    default='lobby',
                    max_length=10,
                )),
                ('questions_json', models.JSONField(default=list)),
                ('current_index', models.IntegerField(default=0)),
                ('time_limit_seconds', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='multiplayer_sessions', to='exams.exam')),
                ('host', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='hosted_sessions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='MultiplayerParticipant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(max_length=64)),
                ('display_name', models.CharField(max_length=64)),
                ('score', models.IntegerField(default=0)),
                ('answers_json', models.JSONField(default=dict)),
                ('connected', models.BooleanField(default=True)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participants', to='multiplayer.multiplayersession')),
            ],
        ),
        migrations.AddConstraint(
            model_name='multiplayerparticipant',
            constraint=models.UniqueConstraint(fields=('session', 'client_id'), name='uniq_session_client'),
        ),
    ]
