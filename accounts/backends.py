from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from accounts.access_codes import get_user_by_access_code, normalize_access_code


class CaseInsensitiveModelBackend(ModelBackend):
    """Authenticate usernames without regard to letter case (Ngoni == ngoni)."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            user = UserModel._default_manager.get(
                **{f"{UserModel.USERNAME_FIELD}__iexact": username}
            )
        except UserModel.DoesNotExist:
            # Run the hasher once to reduce timing differences (#20760).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Prefer an exact-cased match if legacy duplicates exist.
            field = UserModel.USERNAME_FIELD
            qs = UserModel._default_manager.filter(**{f"{field}__iexact": username})
            user = qs.filter(**{field: username}).first() or qs.order_by("pk").first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None


class AccessCodeBackend(ModelBackend):
    """Authenticate staff with a unique 4-digit access code."""

    def authenticate(self, request, username=None, password=None, access_code=None, **kwargs):
        code = normalize_access_code(access_code)
        if not code and username and password in (None, ""):
            # Web login form can submit the code in the username field.
            code = normalize_access_code(username)
        if not code:
            return None

        user = get_user_by_access_code(code)
        if user is not None and self.user_can_authenticate(user):
            return user
        return None
