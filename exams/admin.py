from django.contrib import admin

from .models import AppSettings, Attempt, Exam, Question


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'bonus_window_seconds')
    inlines = [QuestionInline]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('exam', 'user', 'finished_at', 'num_correct', 'num_questions', 'points_earned')
    list_filter = ('exam', 'user')


admin.site.register(AppSettings)
