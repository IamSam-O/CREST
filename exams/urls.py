from django.urls import path

from . import views

urlpatterns = [
    path('exams', views.exam_list),
    path('exams/<int:exam_id>', views.exam_detail),
    path('exams/<int:exam_id>/settings', views.exam_settings),
    path('exams/<int:exam_id>/export', views.exam_export),
    path('exams/<int:exam_id>/import', views.exam_import),
    path('exams/<int:exam_id>/questions', views.exam_questions),
    path('exams/<int:exam_id>/start', views.exam_start),
    path('exams/<int:exam_id>/progress', views.exam_progress),
    path('exams/<int:exam_id>/submit', views.exam_submit),
    path('exams/<int:exam_id>/attempts', views.exam_attempts),
    path('attempts/<int:attempt_id>', views.attempt_detail),
    path('questions/<int:question_id>', views.question_detail),
    path('questions/<int:question_id>/check', views.question_check),
    path('settings', views.app_settings),
    path('groups', views.group_list),
]
