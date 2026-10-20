from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("DevTracker", {"fields": ("global_role", "github_username")}),)
    list_display = ("username", "email", "github_username", "global_role", "is_active")
    list_filter = ("global_role", "is_active")
