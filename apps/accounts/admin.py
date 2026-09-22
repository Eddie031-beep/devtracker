from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("DevTracker", {"fields": ("global_role",)}),)
    list_display = ("username", "email", "global_role", "is_active")
    list_filter = ("global_role", "is_active")
