from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


class RequirePasswordChangeMiddleware:
    """Server-enforced gate: while must_change_password is set, every
    authenticated request (page or API) is redirected/blocked until the
    user changes their password, not just hidden client-side after login."""

    EXEMPT_PATH_NAMES = {'password_change', 'password_change_done', 'logout'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and getattr(user, 'must_change_password', False):
            from django.urls import resolve

            try:
                match = resolve(request.path_info)
            except Exception:
                match = None
            if not match or match.url_name not in self.EXEMPT_PATH_NAMES:
                if request.path_info.startswith('/api/'):
                    return JsonResponse({'error': 'Password change required.'}, status=403)
                return redirect(reverse('password_change'))
        return self.get_response(request)
