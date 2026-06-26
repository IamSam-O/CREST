from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0002_exam_owner_and_groups'),
    ]

    operations = [
        migrations.CreateModel(
            name='GradeScale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('entries_json', models.JSONField(default=list)),
            ],
        ),
        migrations.AddField(
            model_name='exam',
            name='grade_scale',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='exams',
                to='exams.gradescale',
            ),
        ),
    ]
