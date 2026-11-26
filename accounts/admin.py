from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = [*BaseUserAdmin.fieldsets, ("Email", {"fields": ["email_opt_out"]})]
    list_filter = [*BaseUserAdmin.list_filter, "email_opt_out"]
