# referrals/urls.py
from django.urls import path
from . import views

app_name = "referrals"

urlpatterns = [
    path("", views.list_referrals, name="index"),
    path("new/", views.create_referral, name="new"),
    path("<int:pk>/", views.detail_referral, name="detail"),
    path("<int:pk>/assign/", views.assign_referral, name="assign"),
    path("<int:pk>/reply/", views.reply_referral, name="reply"),
    path("<int:pk>/close/", views.close_referral, name="close"),

    # === نموذج بيانات الموجّه ===
    # الاسم المعتمد:
    path("<int:pk>/counselor/", views.counselor_intake_view, name="counselor_intake"),
    # Alias للحفاظ على القوالب القديمة بدون أي تعديل:
    path("<int:pk>/counselor/", views.counselor_intake_view, name="counselor"),

    # ملف الطالب
    path("student/<str:key>/", views.student_file, name="student_file"),
]
