from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

from .models import StaffProfile

User = get_user_model()


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    extra = 0
    max_num = 1


class UserAdmin(BaseUserAdmin):
    inlines = [StaffProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
