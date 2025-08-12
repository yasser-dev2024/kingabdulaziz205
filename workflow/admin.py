from django.contrib import admin

# أمثلة للتسجيل لاحقًا عند إنشاء النماذج:
# from .models import TransitionRule, Notification, ReportSnapshot
#
# @admin.register(TransitionRule)
# class TransitionRuleAdmin(admin.ModelAdmin):
#     list_display = ("from_state", "to_state", "allowed_role", "active")
#     list_filter = ("allowed_role", "active")
#
# @admin.register(Notification)
# class NotificationAdmin(admin.ModelAdmin):
#     list_display = ("target", "channel", "status", "created_at")
#     list_filter = ("channel", "status")
#
# @admin.register(ReportSnapshot)
# class ReportSnapshotAdmin(admin.ModelAdmin):
#     list_display = ("period_start", "period_end", "created_at")
