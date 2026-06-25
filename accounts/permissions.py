from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import BasePermission


class NoTokenAuthOnGameplay(BasePermission):
    """Hardcoded, not role-configurable: rejects token auth outright on
    gameplay endpoints (start/check/submit/progress and multiplayer host
    control), regardless of permissions. This is the "API replicates
    everything except taking tests" boundary."""

    def has_permission(self, request, view):
        return not isinstance(request.successful_authenticator, TokenAuthentication)
