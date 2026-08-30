from django.test import Client

from .auth_security import AUTH_VERSION_SESSION_KEY, current_auth_version


class AuthVersionTestClient(Client):
    """Test-only helper that models the real post-login auth-version binding."""

    def force_login(self, user, backend=None):
        super().force_login(user, backend=backend)
        session = self.session
        session[AUTH_VERSION_SESSION_KEY] = current_auth_version(user)
        session.save()
