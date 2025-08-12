from django.contrib import admin
from .models import Referral, Attachment, Action, ActionAttachment

@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ("reference", "student_name", "grade", "referral_type", "status", "created_by", "created_at")
    list_filter = ("status", "referral_type", "grade", "created_at")
    search_fields = ("reference", "student_name", "created_by__username")
    date_hierarchy = "created_at"

@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("referral", "uploaded_by", "uploaded_at")
    search_fields = ("referral__reference", "uploaded_by__username")

@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = ("referral", "author", "kind", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("referral__reference", "author__username", "content")

@admin.register(ActionAttachment)
class ActionAttachmentAdmin(admin.ModelAdmin):
    list_display = ("action", "uploaded_by", "uploaded_at")
