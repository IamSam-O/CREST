from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_role_settings_is_admin'),
    ]

    operations = [
        migrations.DeleteModel(
            name='RoleSettings',
        ),
    ]
