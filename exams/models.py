import random
import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models.functions import Lower


class GradeScale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    entries_json = models.JSONField(default=list)

    def compute_grade(self, percent):
        ops = {'==': lambda a, b: a == b, '<': lambda a, b: a < b, '>': lambda a, b: a > b,
               '>=': lambda a, b: a >= b, '<=': lambda a, b: a <= b}
        for entry in self.entries_json:
            fn = ops.get(entry.get('operator', '>='))
            if fn and fn(percent, entry.get('value', 0)):
                return entry.get('grade', '')
        return None

    def __str__(self):
        return self.name


class QuestionBank(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    source_filename = models.CharField(max_length=255, null=True, blank=True)
    keywords = models.CharField(max_length=2000, default='', blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_banks',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('name'), name='uniq_bank_name_nocase'),
        ]

    def __str__(self):
        return self.name


class Question(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    SINGLE = 'single'
    MULTI = 'multi'
    TYPE_CHOICES = [(SINGLE, 'single'), (MULTI, 'multi')]

    bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name='questions')
    category = models.CharField(max_length=100, default='', blank=True)
    question_text = models.TextField()
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    points = models.PositiveIntegerField(default=1)
    image_link = models.TextField(null=True, blank=True)
    explanation = models.TextField(null=True, blank=True)
    sort_order = models.IntegerField()

    class Meta:
        ordering = ['sort_order']


class Option(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.IntegerField()

    class Meta:
        ordering = ['sort_order']


class Exam(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    question_bank = models.ForeignKey(
        QuestionBank, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams',
    )
    question_count = models.PositiveIntegerField(default=10)
    # {"Category": weight_percent, ...} — weights sum ≤ 100; remainder fills from the full pool
    category_weights = models.JSONField(default=dict, blank=True)
    bonus_window_seconds = models.PositiveIntegerField(default=30)
    grade_scale = models.ForeignKey(
        GradeScale, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams',
    )
    allowed_groups = models.ManyToManyField(Group, blank=True, related_name='accessible_exams')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_exams',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('name'), name='uniq_exam_name_nocase'),
        ]

    def __str__(self):
        return self.name

    def sample_questions(self):
        if not self.question_bank_id:
            return []
        all_qs = list(self.question_bank.questions.order_by('sort_order'))
        count = min(self.question_count, len(all_qs))
        if not count:
            return []
        if not self.category_weights:
            return random.sample(all_qs, count)
        by_cat = {}
        for q in all_qs:
            by_cat.setdefault(q.category or '', []).append(q)
        selected, used = [], set()
        for cat, weight in self.category_weights.items():
            pool = [q for q in by_cat.get(cat, []) if q.id not in used]
            drawn = random.sample(pool, min(round(count * weight / 100), len(pool)))
            selected.extend(drawn)
            used.update(q.id for q in drawn)
        leftover = [q for q in all_qs if q.id not in used]
        if len(selected) < count:
            selected.extend(random.sample(leftover, min(count - len(selected), len(leftover))))
        return selected


class ExamInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='instances')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_instances',
    )
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(auto_now_add=True)
    num_questions = models.PositiveIntegerField()
    num_correct = models.PositiveIntegerField()
    total_points = models.PositiveIntegerField(default=0)
    points_earned = models.PositiveIntegerField(default=0)
    grade = models.CharField(max_length=20, null=True, blank=True)
    grade_scale = models.ForeignKey(
        GradeScale, on_delete=models.SET_NULL, null=True, blank=True, related_name='instance_grades',
    )
    grade_log = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-finished_at']


class ExamInstanceAnswer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(ExamInstance, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='+')
    selected_option_ids = models.JSONField(default=list)
    is_correct = models.BooleanField()
    points_awarded = models.PositiveIntegerField(default=0)


class InProgressInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='in_progress_instances')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='in_progress_instances',
    )
    questions_json = models.JSONField()
    answers_json = models.JSONField()
    checked_json = models.JSONField()
    elapsed_seconds_json = models.JSONField(default=list)
    current_index = models.IntegerField(default=0)
    total_questions = models.IntegerField()
    started_at = models.DateTimeField()
    multiplier = models.IntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['exam', 'user'], name='uniq_inprogress_exam_user'),
        ]


class AppSettings(models.Model):
    id = models.PositiveIntegerField(primary_key=True, default=1)
    sound_effects_enabled = models.BooleanField(default=False)
    theme = models.CharField(max_length=10, default='dark')
    max_in_progress_instances = models.PositiveIntegerField(default=5)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
