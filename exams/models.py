from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models.functions import Lower


_GRADE_OPS = {
    '==': lambda p, v: p == v,
    '<':  lambda p, v: p < v,
    '>':  lambda p, v: p > v,
    '>=': lambda p, v: p >= v,
    '<=': lambda p, v: p <= v,
}


class GradeScale(models.Model):
    name = models.CharField(max_length=100, unique=True)
    # [{value: int, operator: str, grade: str}] — evaluated in order, first match wins
    entries_json = models.JSONField(default=list)

    def compute_grade(self, percent):
        for entry in self.entries_json:
            fn = _GRADE_OPS.get(entry.get('operator', '>='))
            if fn and fn(percent, entry.get('value', 0)):
                return entry.get('grade', '')
        return None

    def __str__(self):
        return self.name


class Exam(models.Model):
    name = models.CharField(max_length=255)
    source_filename = models.CharField(max_length=255, null=True, blank=True)
    bonus_window_seconds = models.PositiveIntegerField(default=30)
    keywords = models.CharField(max_length=2000, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Null for legacy exams created before ownership existed - treated as
    # admin-only to edit (see accounts.permissions.is_admin_user) but still
    # publicly visible like any other exam with no allowed_groups.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_exams',
    )
    # Empty = visible/practicable by everyone (today's behavior). Non-empty
    # restricts visibility to members of these groups, plus the owner and admins.
    allowed_groups = models.ManyToManyField(Group, blank=True, related_name='accessible_exams')
    grade_scale = models.ForeignKey(
        GradeScale, on_delete=models.SET_NULL, null=True, blank=True, related_name='exams',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('name'), name='uniq_exam_name_nocase'),
        ]

    def __str__(self):
        return self.name


class Question(models.Model):
    SINGLE = 'single'
    MULTI = 'multi'
    TYPE_CHOICES = [(SINGLE, 'single'), (MULTI, 'multi')]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    points = models.PositiveIntegerField(default=1)
    image_link = models.TextField(null=True, blank=True)
    explanation = models.TextField(null=True, blank=True)
    sort_order = models.IntegerField()

    class Meta:
        ordering = ['sort_order']


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    option_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.IntegerField()

    class Meta:
        ordering = ['sort_order']


class Attempt(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(auto_now_add=True)
    num_questions = models.PositiveIntegerField()
    num_correct = models.PositiveIntegerField()
    total_points = models.PositiveIntegerField(default=0)
    points_earned = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-finished_at']


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='+')
    selected_option_ids = models.JSONField(default=list)
    is_correct = models.BooleanField()
    points_awarded = models.PositiveIntegerField(default=0)


class InProgressAttempt(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='in_progress_attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='in_progress_attempts')
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
    """Singleton row (manual get_or_create(pk=1), matches the existing
    single-row app_settings table)."""

    id = models.PositiveIntegerField(primary_key=True, default=1)
    sound_effects_enabled = models.BooleanField(default=False)
    theme = models.CharField(max_length=10, default='dark')
    max_in_progress_instances = models.PositiveIntegerField(default=5)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
