from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import ThemedAuthenticationForm

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(authentication_form=ThemedAuthenticationForm), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password-change/', views.PasswordChangeView.as_view(), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    path('invite/<str:token>/', views.InviteAcceptView.as_view(), name='invite_accept'),
]
