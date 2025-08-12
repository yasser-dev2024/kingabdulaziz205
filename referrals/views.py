from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _

from .models import Referral, Attachment, Action, ActionAttachment

# إعدادات المرفقات
ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5


# -----------------------------
# أدوات مساعدة
# -----------------------------
def _ctx(form=None, errors=None):
    return {
        "form": form or {},
        "errors": errors or {},
        "grades": Referral.GRADE_CHOICES,
        "types": Referral.TYPE_CHOICES,
    }


def _can_view(user, ref: Referral):
    return user.is_staff or user == ref.created_by or (ref.assignee and user == ref.assignee)


def _can_assign(user, ref: Referral):
    return user.is_staff or user == ref.created_by


# -----------------------------
# قائمة الإحالات + العدّادات
# -----------------------------
@login_required
def list_referrals(request):
    user = request.user
    scope = request.GET.get("scope", "all")  # all | sent | inbox

    # جميع الإحالات التي تخص هذا المستخدم (مرسلة منه أو واردة إليه)
    base_qs = (
        Referral.objects
        .select_related("created_by__profile", "assignee__profile")
        .filter(Q(created_by=user) | Q(assignee=user))
        .order_by("-created_at")
        .distinct()
    )

    sent_qs = base_qs.filter(created_by=user)
    inbox_qs = base_qs.filter(assignee=user)
    all_qs = base_qs

    counts = {
        "all": all_qs.count(),
        "sent": sent_qs.count(),
        "inbox": inbox_qs.count(),
    }

    if scope == "sent":
        items = sent_qs
    elif scope == "inbox":
        items = inbox_qs
    else:
        items = all_qs
        scope = "all"

    return render(
        request,
        "referrals/index.html",
        {
            "items": items,
            "counts": counts,
            "scope": scope,
        },
    )


# -----------------------------
# إنشاء إحالة
# -----------------------------
@login_required
@require_http_methods(["GET", "POST"])
def create_referral(request):
    if request.method == "POST":
        student_name = (request.POST.get("student_name") or "").strip()
        grade = (request.POST.get("grade") or "").strip()
        referral_type = (request.POST.get("referral_type") or "").strip()
        details = (request.POST.get("details") or "").strip()
        files = request.FILES.getlist("attachments")

        errors = {}
        if not student_name:
            errors["student_name"] = "اسم الطالب مطلوب."
        if grade not in [g for g, _ in Referral.GRADE_CHOICES]:
            errors["grade"] = "الصف غير صالح."
        if referral_type not in [t for t, _ in Referral.TYPE_CHOICES]:
            errors["referral_type"] = "نوع الإحالة غير صالح."
        if len(details) < 10:
            errors["details"] = "الرجاء إدخال تفاصيل كافية (10 أحرف على الأقل)."

        if len(files) > MAX_FILES:
            errors["attachments"] = f"يمكن رفع {MAX_FILES} ملفات كحد أقصى."

        checked_files = []
        for f in files:
            ext = "." + f.name.split(".")[-1].lower()
            if ext not in ALLOWED_EXTS:
                errors["attachments"] = "نوع ملف غير مسموح."
                break
            if f.size > MAX_FILE_SIZE:
                errors["attachments"] = "حجم الملف يتجاوز 10MB."
                break
            checked_files.append(f)

        if errors:
            return render(request, "referrals/new.html", _ctx(request.POST, errors))

        ref = Referral.objects.create(
            student_name=student_name,
            grade=grade,
            referral_type=referral_type,
            details=details,
            created_by=request.user,
            status="UNDER_REVIEW",
        )
        for f in checked_files:
            Attachment.objects.create(referral=ref, file=f, uploaded_by=request.user)

        messages.success(request, _("تم إنشاء الإحالة بنجاح."))
        return redirect("referrals:detail", pk=ref.pk)

    return render(request, "referrals/new.html", _ctx())


# -----------------------------
# تفاصيل إحالة
# -----------------------------
@login_required
def detail_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه الإحالة.")

    assignable = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by("username")
    actions = (
        Action.objects.filter(referral=ref)
        .select_related("author__profile")
        .prefetch_related("files")
        .order_by("created_at")
    )
    return render(
        request,
        "referrals/detail.html",
        {
            "r": ref,
            "assignable": assignable,
            "actions": actions,
        },
    )


# -----------------------------
# تحويل إحالة
# -----------------------------
@login_required
@require_http_methods(["POST"])
def assign_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_assign(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية تحويل هذه الإحالة.")
    user_id = request.POST.get("assignee")
    try:
        new_assignee = User.objects.get(pk=int(user_id), is_active=True)
    except Exception:
        messages.error(request, "المستخدم المطلوب غير متاح.")
        return redirect("referrals:detail", pk=ref.pk)

    ref.assignee = new_assignee
    if ref.status in ["NEW", "UNDER_REVIEW"]:
        ref.status = "UNDER_REVIEW"
    ref.save()

    Action.objects.create(referral=ref, author=request.user, kind="NOTE", content=f"تحويل إلى {new_assignee.username}")
    messages.success(request, f"تم تحويل الإحالة إلى المستخدم: {new_assignee.username}")
    return redirect("referrals:detail", pk=ref.pk)


# -----------------------------
# رد على إحالة
# -----------------------------
@login_required
@require_http_methods(["POST"])
def reply_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية الرد على هذه الإحالة.")

    content = (request.POST.get("content") or "").strip()
    files = request.FILES.getlist("reply_files")

    if not content and not files:
        messages.error(request, "أضف نصًا أو ملفات للرد.")
        return redirect("referrals:detail", pk=ref.pk)

    if len(files) > MAX_FILES:
        messages.error(request, f"يمكن رفع {MAX_FILES} ملفات كحد أقصى.")
        return redirect("referrals:detail", pk=ref.pk)

    checked = []
    for f in files:
        ext = "." + f.name.split(".")[-1].lower()
        if ext not in ALLOWED_EXTS:
            messages.error(request, "نوع ملف غير مسموح.")
            return redirect("referrals:detail", pk=ref.pk)
        if f.size > MAX_FILE_SIZE:
            messages.error(request, "حجم الملف يتجاوز 10MB.")
            return redirect("referrals:detail", pk=ref.pk)
        checked.append(f)

    act = Action.objects.create(referral=ref, author=request.user, kind="REPLY", content=content)
    for f in checked:
        ActionAttachment.objects.create(action=act, file=f, uploaded_by=request.user)

    if ref.status == "NEW":
        ref.status = "UNDER_REVIEW"
        ref.save()

    messages.success(request, "تم إرسال الرد.")
    return redirect("referrals:detail", pk=ref.pk)


# -----------------------------
# إغلاق إحالة
# -----------------------------
@login_required
@require_http_methods(["POST"])
def close_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية إغلاق هذه الإحالة.")

    if not Action.objects.filter(referral=ref).exists():
        messages.error(request, "لا يمكن إغلاق الإحالة قبل اتخاذ إجراء (رد/ملاحظة/تحويل).")
        return redirect("referrals:detail", pk=ref.pk)

    ref.status = "CLOSED"
    ref.save()
    Action.objects.create(referral=ref, author=request.user, kind="DECISION", content="تم إغلاق الإحالة.")
    messages.success(request, "تم إغلاق الإحالة.")
    return redirect("referrals:detail", pk=ref.pk)
