from django.urls import path

from . import views

urlpatterns = [
    # Question banks (editor/staff managed)
    path('banks', views.bank_list),
    path('banks/<uuid:bank_id>', views.bank_detail),
    path('banks/<uuid:bank_id>/export', views.bank_export),
    path('banks/<uuid:bank_id>/import', views.bank_import),
    path('banks/<uuid:bank_id>/questions', views.bank_questions),
    path('banks/<uuid:bank_id>/categories', views.bank_categories),

    # Exam configs (listed to users; CRUD by editor/staff)
    path('exams', views.exam_list),
    path('exams/<uuid:exam_id>', views.exam_detail),
    path('exams/<uuid:exam_id>/settings', views.exam_settings),

    # Exam instance lifecycle (gameplay)
    path('exams/<uuid:exam_id>/start', views.exam_start),
    path('exams/<uuid:exam_id>/progress', views.exam_progress),
    path('exams/<uuid:exam_id>/submit', views.exam_submit),
    path('exams/<uuid:exam_id>/instances', views.exam_instances),

    # Instance + question detail
    path('instances/<uuid:instance_id>', views.instance_detail),
    path('questions/<uuid:question_id>', views.question_detail),
    path('questions/<uuid:question_id>/check', views.question_check),

    # Global
    path('settings', views.app_settings),
    path('groups', views.group_list),
    path('grade-scales', views.grade_scale_list),
]
