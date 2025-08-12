from django.contrib import admin

# تخصيص واجهة لوحة الإدارة
admin.site.site_header = "لوحة إدارة نظام الإحالات"
admin.site.site_title = "إدارة الإحالات"
admin.site.index_title = "مرحبًا بك في لوحة الإدارة"

# إذا أضفت نموذج ملف مستخدم لاحقًا (مثال):
# from .models import UserProfile
# @admin.register(UserProfile)
# class UserProfileAdmin(admin.ModelAdmin):
#     list_display = ("user", "role", "is_active", "created_at")
#     list_filter = ("role", "is_active")
#     search_fields = ("user__username", "user__first_name", "user__last_name")
