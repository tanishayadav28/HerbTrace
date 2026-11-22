from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class AppUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "approval_status", "is_active")
    list_filter = ("role", "approval_status", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("Traceability", {"fields": ("role", "approval_status", "phone", "organization")}),
    )
