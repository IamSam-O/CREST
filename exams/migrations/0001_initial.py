import uuid
import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AppSettings',
            fields=[
                ('id', models.PositiveIntegerField(default=1, primary_key=True, serialize=False)),
                ('sound_effects_enabled', models.BooleanField(default=False)),
                ('theme', models.CharField(default='dark', max_length=10)),
                ('max_in_progress_instances', models.PositiveIntegerField(default=5)),
            ],
        ),
        migrations.CreateModel(
            name='GradeScale',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('entries_json', models.JSONField(default=list)),
            ],
        ),
        migrations.CreateModel(
            name='QuestionBank',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('source_filename', models.CharField(blank=True, max_length=255, null=True)),
                ('keywords', models.CharField(blank=True, default='', max_length=2000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='owned_banks', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'constraints': [
                models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='uniq_bank_name_nocase'),
            ]},
        ),
        migrations.CreateModel(
            name='Question',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('category', models.CharField(blank=True, default='', max_length=100)),
                ('question_text', models.TextField()),
                ('question_type', models.CharField(choices=[('single', 'single'), ('multi', 'multi')], max_length=10)),
                ('points', models.PositiveIntegerField(default=1)),
                ('image_link', models.TextField(blank=True, null=True)),
                ('explanation', models.TextField(blank=True, null=True)),
                ('sort_order', models.IntegerField()),
                ('bank', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='exams.questionbank')),
            ],
            options={'ordering': ['sort_order']},
        ),
        migrations.CreateModel(
            name='Option',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('option_text', models.TextField()),
                ('is_correct', models.BooleanField(default=False)),
                ('sort_order', models.IntegerField()),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='exams.question')),
            ],
            options={'ordering': ['sort_order']},
        ),
        migrations.CreateModel(
            name='Exam',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('question_count', models.PositiveIntegerField(default=10)),
                ('category_weights', models.JSONField(blank=True, default=dict)),
                ('bonus_window_seconds', models.PositiveIntegerField(default=30)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('allowed_groups', models.ManyToManyField(blank=True, related_name='accessible_exams', to='auth.group')),
                ('grade_scale', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='exams', to='exams.gradescale',
                )),
                ('owner', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='owned_exams', to=settings.AUTH_USER_MODEL,
                )),
                ('question_bank', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='exams', to='exams.questionbank',
                )),
            ],
            options={'constraints': [
                models.UniqueConstraint(django.db.models.functions.text.Lower('name'), name='uniq_exam_name_nocase'),
            ]},
        ),
        migrations.CreateModel(
            name='ExamInstance',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('started_at', models.DateTimeField()),
                ('finished_at', models.DateTimeField(auto_now_add=True)),
                ('num_questions', models.PositiveIntegerField()),
                ('num_correct', models.PositiveIntegerField()),
                ('total_points', models.PositiveIntegerField(default=0)),
                ('points_earned', models.PositiveIntegerField(default=0)),
                ('grade', models.CharField(blank=True, max_length=20, null=True)),
                ('grade_log', models.JSONField(blank=True, default=list)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='instances', to='exams.exam')),
                ('grade_scale', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='instance_grades', to='exams.gradescale',
                )),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_instances', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-finished_at']},
        ),
        migrations.CreateModel(
            name='ExamInstanceAnswer',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('selected_option_ids', models.JSONField(default=list)),
                ('is_correct', models.BooleanField()),
                ('points_awarded', models.PositiveIntegerField(default=0)),
                ('instance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='exams.examinstance')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='exams.question')),
            ],
        ),
        migrations.CreateModel(
            name='InProgressInstance',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('questions_json', models.JSONField()),
                ('answers_json', models.JSONField()),
                ('checked_json', models.JSONField()),
                ('elapsed_seconds_json', models.JSONField(default=list)),
                ('current_index', models.IntegerField(default=0)),
                ('total_questions', models.IntegerField()),
                ('started_at', models.DateTimeField()),
                ('multiplier', models.IntegerField(default=1)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='in_progress_instances', to='exams.exam')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='in_progress_instances', to=settings.AUTH_USER_MODEL)),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=['exam', 'user'], name='uniq_inprogress_exam_user'),
            ]},
        ),
    ]
