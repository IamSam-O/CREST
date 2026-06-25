from django.urls import path

from . import views

urlpatterns = [
    path('', views.host_new, name='mp_host_new'),
    path('host/<str:room_code>/<str:host_secret>/', views.host_room, name='mp_host_room'),
    path('play/<str:token>/', views.play_room, name='mp_play_room'),
]
