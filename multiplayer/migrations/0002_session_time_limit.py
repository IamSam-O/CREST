from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('multiplayer', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='multiplayersession',
            name='time_limit_seconds',
            field=models.IntegerField(default=0),
        ),
    ]
