# C:\Users\Test2\kingabdulaziz205\accounts\admin.py
from django.contrib import admin
from django.contrib.auth.models import User
from .models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "role", "user")
    search_fields = ("full_name", "user__username")
    list_filter = ("role",)
