from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0003_grade_scale'),
    ]

    operations = [
        migrations.AddField(
            model_name='attempt',
            name='grade',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
