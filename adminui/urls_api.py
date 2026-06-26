from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import viewsets

router = DefaultRouter()
router.register('users', viewsets.UserViewSet)
router.register('groups', viewsets.GroupViewSet)
router.register('invites', viewsets.InviteViewSet)
router.register('attempts', viewsets.AttemptViewSet)
router.register('grade-scales', viewsets.GradeScaleViewSet)
router.register('sessions', viewsets.MultiplayerSessionViewSet)
router.register('participants', viewsets.MultiplayerParticipantViewSet, basename='admin-participant')

urlpatterns = [
    path('app-settings/', viewsets.app_settings_view),
    path('email-settings/', viewsets.email_settings_view),
    path('whoami/', viewsets.whoami_view),
    path('exams/', viewsets.exam_options_view),
    path('', include(router.urls)),
]
