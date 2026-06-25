from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('multiplayer', '0002_session_time_limit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='multiplayersession',
            name='status',
            field=models.CharField(
                choices=[
                    ('lobby', 'lobby'),
                    ('active', 'active'),
                    ('paused', 'paused'),
                    ('finished', 'finished'),
                    ('abandoned', 'abandoned'),
                ],
                default='lobby',
                max_length=10,
            ),
        ),
    ]
