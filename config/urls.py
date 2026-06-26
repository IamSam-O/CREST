import os

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.views import redirect_to_login
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve as static_serve
from adminui import views as adminui_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from accounts.views import my_token, send_test_email, test_email_connection

urlpatterns = [
    # Resolved before admin.site.urls registers its own admin/login/ route,
    # so there's one login page site-wide instead of Django admin's separate
    # built-in form - ?next= is preserved so login bounces back to /admin/.
    path('admin/login/', RedirectView.as_view(url='/accounts/login/', query_string=True)),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('multiplayer/', include('multiplayer.urls')),
    path('manage/', adminui_views.admin_ui_index, name='adminui_index'),
    path('api/auth/token/', obtain_auth_token),
    path('api/account/token/', my_token),
    path('api/admin/email/test/', test_email_connection),
    path('api/admin/email/send-test/', send_test_email),
    path('api/admin/manage/', include('adminui.urls_api')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='api-docs'),
    path('api/', include('exams.urls')),
]


def _serve_frontend(request, path=''):
    # Serve real static assets (JS, CSS, fonts, images) directly without auth.
    # Everything else is an SPA route — gate on auth and serve index.html so
    # the Vue router handles it client-side (SPA fallback pattern).
    if path and path != 'index.html' and os.path.isfile(os.path.join(settings.PUBLIC_DIR, path)):
        return static_serve(request, path, document_root=settings.PUBLIC_DIR)
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    return static_serve(request, 'index.html', document_root=settings.PUBLIC_DIR)


# Matches the existing express.static(public) mount at "/" — must stay last
# so it doesn't shadow the API/admin/accounts routes above.
urlpatterns += [
    re_path(r'^(?P<path>.*)$', _serve_frontend),
]
