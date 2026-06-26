import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0005_attempt_grade_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='attempt',
            name='grade_scale',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='attempt_grades',
                to='exams.gradescale',
            ),
        ),
    ]
