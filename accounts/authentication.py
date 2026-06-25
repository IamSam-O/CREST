from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """app.js makes plain same-origin fetch() calls with no CSRF-token
    plumbing (none existed under Express either). SESSION_COOKIE_SAMESITE
    ='Lax' is the actual mitigation for this same-origin SPA+API; this
    class just stops DRF's default CSRF enforcement from rejecting those
    requests. Token auth (see permissions.py) has no CSRF exposure and is
    unaffected by this."""

    def enforce_csrf(self, request):
        return
