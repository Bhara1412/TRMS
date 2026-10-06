from django.contrib.auth.backends import ModelBackend
from django.conf import settings
from django.contrib.auth.hashers import check_password
from functools import lru_cache
from .models import User

@lru_cache(maxsize=512)
def uses_demo_password(encoded_password):
    # Recheck when the encoded password changes, without rehashing on every page.
    return check_password('DemoPass!234', encoded_password)

class CurrentRoleBackend(ModelBackend):
    def user_can_authenticate(self, user):
        if not settings.DEBUG and uses_demo_password(user.password):
            return False
        return super().user_can_authenticate(user)
    def has_perm(self, user_obj, perm, obj=None):
        if user_obj.role != User.Role.ADMIN:
            return False
        return super().has_perm(user_obj, perm, obj)
    def get_user(self, user_id):
        user=super().get_user(user_id)
        if user is not None and user.role != User.Role.ADMIN:
            # A former administrator must not retain Django-admin access.
            user.is_staff=False
            user.is_superuser=False
        return user
