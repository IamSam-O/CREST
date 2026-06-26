from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0004_attempt_grade'),
    ]

    operations = [
        migrations.AddField(
            model_name='attempt',
            name='grade_log',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
