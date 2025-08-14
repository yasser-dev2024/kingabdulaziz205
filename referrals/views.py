# referrals/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from django.http import HttpResponseForbidden, HttpRequest
from django.db.models import Q
import unicodedata, re

from accounts.models import Profile
from .models import Referral, Attachment, Action, ActionAttachment

# (اختياري) دعم نموذج الموجّه إذا كان موجودًا في مشروعك
try:
    from .models import CounselorIntake
    from .forms import CounselorIntakeForm
    HAS_COUNSELOR = True
except Exception:
    HAS_COUNSELOR = False

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5


# =============== أدوات مساعدة ===============

def _ctx(form=None, errors=None):
    return {
        "form": form or {},
        "errors": errors or {},
        "grades": Referral.GRADE_CHOICES,
        "types": Referral.TYPE_CHOICES,
    }

def _can_view(user, ref: Referral):
    return user.is_staff or user == ref.created_by or (ref.assignee and user == ref.assignee)

def _is_counselor(user):
    try:
        return user.profile.role == "موجه طلابي"
    except Profile.DoesNotExist:
        return False

def _can_assign(user, ref: Referral):
    # نسمح للمنشئ، المشرف، الموجّه، و"المكلّف الحالي" بالتحويل
    return (
        user.is_staff
        or user == ref.created_by
        or _is_counselor(user)
        or (ref.assignee_id == user.id)
    )

def _make_student_key(name: str, civil_id: str | None = None) -> str:
    """يصنع مفتاح تجميعي للطالب من السجل المدني (إن وُجد) أو من الاسم."""
    key = (civil_id or "").strip()
    if not key:
        s = unicodedata.normalize("NFKC", (name or "").strip())
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"[^0-9A-Za-z\u0600-\u06FF\-]", "", s)
        key = s[:60]
    return key

def _ensure_student_key(ref: Referral):
    """يضمن وجود student_key ويحفظه عند اللزوم (إن كان الحقل موجوداً)."""
    try:
        has_key_field = hasattr(ref, "student_key")
    except Exception:
        has_key_field = False

    if not has_key_field:
        return

    try:
        current = getattr(ref, "student_key", "") or ""
        if current:
            return
        civil = ""
        try:
            civil = (getattr(ref, "student_civil_id", None) or "")[:64]
        except Exception:
            civil = ""
        new_key = _make_student_key(getattr(ref, "student_name", ""), civil)
        if new_key:
            ref.student_key = new_key
            ref.save(update_fields=["student_key"])
    except Exception:
        pass


def _render_counselor_summary(intake) -> str:
    """ملخّص عربي مرتب لحقول نموذج الموجّه."""
    if not intake:
        return ""
    lines = ["ملخّص بيانات الموجّه الطلابي:"]
    skip = {"id", "referral", "created_at", "updated_at"}
    for f in intake._meta.fields:
        if f.name in skip:
            continue
        label = getattr(f, "verbose_name", f.name)
        val = getattr(intake, f.name, None)
        if val in (None, ""):
            continue
        if isinstance(val, bool):
            val = "نعم" if val else "لا"
        lines.append(f"- {label}: {val}")
    return "\n".join(lines)


# =============== القائمة + العدّادات/الفلاتر (مع تجميع حسب الطالب) ===============

@login_required
def list_referrals(request: HttpRequest):
    scope = request.GET.get("scope", "all")

    sent_qs = Referral.objects.filter(created_by=request.user)
    inbox_qs = Referral.objects.filter(assignee=request.user)

    if scope == "sent":
        items_qs = sent_qs
    elif scope == "inbox":
        items_qs = inbox_qs
    else:
        items_qs = Referral.objects.filter(
            Q(created_by=request.user) | Q(assignee=request.user)
        )

    items_qs = items_qs.select_related("created_by", "assignee").order_by("-created_at")
    items = list(items_qs)

    # نضمن وجود student_key ثم نجمّع حسبه
    for r in items:
        _ensure_student_key(r)

    groups_map = {}
    for r in items:
        key = getattr(r, "student_key", "") or f"ref-{r.pk}"
        g = groups_map.get(key)
        if not g:
            g = {
                "key": getattr(r, "student_key", "") or "",
                "student_name": r.student_name,
                "latest": r.created_at,
                "referrals": [],
            }
            groups_map[key] = g
        g["referrals"].append(r)
        if r.created_at > g["latest"]:
            g["latest"] = r.created_at
        # لو تعدد الاسم نأخذ الأحدث
        if r.created_at >= g["latest"]:
            g["student_name"] = r.student_name

    groups = sorted(groups_map.values(), key=lambda x: x["latest"], reverse=True)

    counts = {
        "all": Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user)).count(),
        "sent": sent_qs.count(),
        "inbox": inbox_qs.count(),
    }

    return render(request, "referrals/index.html", {
        "items": items,      # متروك لو احتجته لاحقًا
        "groups": groups,    # << التجميع الجديد
        "counts": counts,
        "scope": scope,
    })


# =============== إنشاء إحالة ===============

@login_required
@require_http_methods(["GET", "POST"])
def create_referral(request):
    if request.method == "POST":
        student_name = (request.POST.get("student_name") or "").strip()
        grade = (request.POST.get("grade") or "").strip()
        referral_type = (request.POST.get("referral_type") or "").strip()
        details = (request.POST.get("details") or "").strip()
        student_civil_id = (request.POST.get("student_civil_id") or "").strip()
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

        updated_fields = []
        try:
            if hasattr(ref, "student_civil_id"):
                ref.student_civil_id = student_civil_id or None
                updated_fields.append("student_civil_id")
        except Exception:
            pass

        try:
            if hasattr(ref, "student_key"):
                ref.student_key = _make_student_key(student_name, student_civil_id)
                updated_fields.append("student_key")
        except Exception:
            pass

        if updated_fields:
            try:
                ref.save(update_fields=updated_fields)
            except Exception:
                pass

        for f in checked_files:
            Attachment.objects.create(referral=ref, file=f, uploaded_by=request.user)

        counselor = User.objects.filter(is_active=True, profile__role="موجه طلابي").first()
        if counselor:
            ref.assignee = counselor
            ref.status = "UNDER_REVIEW"
            ref.save(update_fields=["assignee", "status"])
            Action.objects.create(
                referral=ref, author=request.user, kind="NOTE",
                content=f"تحويل تلقائي إلى الموجّه الطلابي: {counselor.username}"
            )

        messages.success(request, _("تم إنشاء الإحالة بنجاح."))
        return redirect("referrals:detail", pk=ref.pk)

    return render(request, "referrals/new.html", _ctx())


# =============== تفاصيل الإحالة ===============

@login_required
def detail_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه الإحالة.")

    _ensure_student_key(ref)

    assignable = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by("username")
    actions = (
        Action.objects.filter(referral=ref)
        .select_related("author")
        .prefetch_related("files")
        .order_by("created_at")
    )
    is_counselor = _is_counselor(request.user)

    same_student_qs = Referral.objects.filter(
        Q(created_by=request.user) | Q(assignee=request.user)
    ).exclude(pk=ref.pk).order_by("-created_at")
    same_student = []
    for r in same_student_qs:
        _ensure_student_key(r)
        if hasattr(ref, "student_key") and hasattr(r, "student_key") and r.student_key and ref.student_key:
            if r.student_key == ref.student_key:
                same_student.append(r)
        if len(same_student) >= 10:
            break

    files = getattr(ref, "attachments", Attachment.objects.none()).all()

    return render(request, "referrals/detail.html", {
        "r": ref,
        "assignable": assignable,
        "actions": actions,
        "is_counselor": is_counselor,
        "same_student": same_student,
        "files": files,
    })


# =============== تحويل الإحالة ===============

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

    Action.objects.create(
        referral=ref, author=request.user, kind="NOTE",
        content=f"تحويل إلى {new_assignee.username}"
    )

    if HAS_COUNSELOR and _is_counselor(request.user):
        intake = CounselorIntake.objects.filter(referral=ref).first()
        if intake:
            summary = _render_counselor_summary(intake)
            if summary:
                Action.objects.create(
                    referral=ref, author=request.user, kind="NOTE", content=summary
                )

    messages.success(request, f"تم تحويل الإحالة إلى المستخدم: {new_assignee.username}")
    return redirect("referrals:detail", pk=ref.pk)


# =============== رد ===============

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


# =============== إغلاق ===============

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


# =============== شاشة الموجّه (اختياري) ===============

@login_required
@require_http_methods(["GET", "POST"])
def counselor_intake_view(request, pk: int):
    if not HAS_COUNSELOR:
        return HttpResponseForbidden("هذه الصفحة غير مفعّلة.")
    ref = get_object_or_404(Referral, pk=pk)
    try:
        if request.user.profile.role != "موجه طلابي":
            return HttpResponseForbidden("هذه الصفحة للموجّه الطلابي فقط.")
    except Profile.DoesNotExist:
        return HttpResponseForbidden("هذه الصفحة للموجّه الطلابي فقط.")

    intake, _ = CounselorIntake.objects.get_or_create(referral=ref)

    if request.method == "POST":
        form = CounselorIntakeForm(request.POST, instance=intake)
        if form.is_valid():
            form.save()
            messages.success(request, "تم حفظ نموذج الموجّه.")
            return redirect("referrals:detail", pk=ref.pk)
    else:
        form = CounselorIntakeForm(instance=intake)

    return render(request, "referrals/counselor_form.html", {"r": ref, "form": form})


# =============== ملف الطالب ===============

@login_required
def student_file(request, key: str):
    visible_qs = Referral.objects.filter(
        Q(created_by=request.user) | Q(assignee=request.user)
    ).order_by("-created_at")
    visible = list(visible_qs)

    for r in visible:
        _ensure_student_key(r)

    items = [r for r in visible if getattr(r, "student_key", "") == key]
    student_name = items[0].student_name if items else ""

    return render(request, "referrals/student_file.html", {
        "student_name": student_name,
        "items": items,
        "key": key,
    })
