from django.contrib import admin

from .models import AppSettings, Exam, ExamInstance, Question, QuestionBank


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'owner')
    inlines = [QuestionInline]


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('name', 'question_bank', 'question_count', 'created_at')


@admin.register(ExamInstance)
class ExamInstanceAdmin(admin.ModelAdmin):
    list_display = ('exam', 'user', 'finished_at', 'num_correct', 'num_questions', 'points_earned')
    list_filter = ('exam', 'user')


admin.site.register(AppSettings)
