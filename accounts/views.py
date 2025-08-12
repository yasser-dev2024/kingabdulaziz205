from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User, Group
from django.db import IntegrityError
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

# الأدوار المسموح بها (سيتم إنشاء Group بنفس الاسم تلقائيًا إن لم يوجد)
ROLES = [
    "وكيل الشؤون المدرسية",
    "وكيل الشؤون التعليمية",
    "وكيل شؤون الطلاب",
    "موجه طلابي",
    "إداري",
    "مدير المدرسة",
]

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.method == "POST":
        username    = (request.POST.get("username") or "").strip()
        password    = (request.POST.get("password") or "").strip()
        password2   = (request.POST.get("password2") or "").strip()
        school_code = (request.POST.get("school_code") or "").strip()
        role        = (request.POST.get("role") or "").strip()

        errors = {}
        # رمز المدرسة (لا نكشف تفاصيل أكثر)
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

        if errors:
            return render(
                request,
                "accounts/register.html",
                {"errors": errors, "form": {"username": username, "role": role}, "roles": ROLES},
            )

        # إنشاء المستخدم + التعامل مع اسم مستخدم مكرر
        try:
            user = User.objects.create_user(username=username, password=password)
        except IntegrityError:
            return render(
                request,
                "accounts/register.html",
                {"errors": {"username": "اسم المستخدم مستخدم مسبقًا."},
                 "form": {"username": username, "role": role},
                 "roles": ROLES},
            )

        # ربطه بالمجموعة حسب الدور
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

        messages.success(request, "تم إنشاء الحساب بنجاح، تفضّل بتسجيل الدخول.")
        return redirect("accounts:login")

    # GET
    return render(request, "accounts/register.html", {"roles": ROLES})
