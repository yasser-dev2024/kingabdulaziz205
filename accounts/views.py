# C:\Users\Test2\kingabdulaziz205\accounts\views.py
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.db import IntegrityError
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .models import Profile, ROLE_CHOICES

ROLES = [r[0] for r in ROLE_CHOICES]  # أسماء الأدوار فقط

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.method == "POST":
        username    = (request.POST.get("username") or "").strip()
        password    = (request.POST.get("password") or "").strip()
        password2   = (request.POST.get("password2") or "").strip()
        school_code = (request.POST.get("school_code") or "").strip()
        role        = (request.POST.get("role") or "").strip()
        full_name   = (request.POST.get("full_name") or "").strip()

        errors = {}

        # رمز المدرسة
        if school_code != getattr(settings, "SCHOOL_SECRET_CODE", ""):
            errors["school_code"] = "رمز المدرسة غير صحيح."

        # التحقق الأساسي
        if not username:
            errors["username"] = "اسم المستخدم مطلوب."
        if len(password) < 8:
            errors["password"] = "كلمة المرور يجب أن تكون 8 أحرف على الأقل."
        if password != password2:
            errors["password2"] = "تأكيد كلمة المرور غير مطابق."
        if role not in ROLES:
            errors["role"] = "اختر نوع المستخدم."
        # الاسم الثلاثي: 3 كلمات على الأقل
        if len(full_name.split()) < 3 or len(full_name) < 8:
            errors["full_name"] = "اكتب الاسم الثلاثي الكامل."

        if errors:
            return render(
                request,
                "accounts/register.html",
                {
                    "errors": errors,
                    "form": {"username": username, "role": role, "full_name": full_name},
                    "roles": ROLES,
                },
            )

        # إنشاء المستخدم
        try:
            user = User.objects.create_user(username=username, password=password, is_active=True)
        except IntegrityError:
            return render(
                request,
                "accounts/register.html",
                {
                    "errors": {"username": "اسم المستخدم مستخدم مسبقًا."},
                    "form": {"username": username, "role": role, "full_name": full_name},
                    "roles": ROLES,
                },
            )

        # إنشاء/حفظ الملف الشخصي
        Profile.objects.create(user=user, full_name=full_name, role=role)

        # ربطه بالمجموعة حسب الدور
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

        messages.success(request, "تم إنشاء الحساب بنجاح، تفضّل بتسجيل الدخول.")
        return redirect("accounts:login")

    # GET
    return render(request, "accounts/register.html", {"roles": ROLES})
