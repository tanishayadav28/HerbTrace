from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with either username or e-mail address (case-insensitive)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if not username or password is None:
            return None
        candidates = User.objects.filter(username__iexact=username) | User.objects.filter(
            email__iexact=username
        )
        for user in candidates.distinct()[:2]:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        # Run the hasher once to reduce timing differences for unknown users.
        User().set_password(password)
        return None
