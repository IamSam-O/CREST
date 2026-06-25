from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/multiplayer/<str:room_code>/', consumers.MultiplayerConsumer.as_asgi()),
]
