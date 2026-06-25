from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='rolesettings',
            name='api_access_allowed',
        ),
        migrations.AddField(
            model_name='rolesettings',
            name='is_admin',
            field=models.BooleanField(default=False),
        ),
    ]
