import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('exams', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='owner',
            field=models.ForeignKey(
                null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='owned_exams', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='exam',
            name='allowed_groups',
            field=models.ManyToManyField(blank=True, related_name='accessible_exams', to='auth.group'),
        ),
    ]
