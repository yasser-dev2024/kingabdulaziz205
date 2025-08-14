from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from django.http import HttpResponseForbidden, HttpRequest
from django.db.models import Q

from accounts.models import Profile
from .models import Referral, Attachment, Action, ActionAttachment, CounselorIntake
from .forms import CounselorIntakeForm

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5


def _ctx(form=None, errors=None):
    return {
        "form": form or {},
        "errors": errors or {},
        "grades": Referral.GRADE_CHOICES,
        "types": Referral.TYPE_CHOICES,
    }


def _is_counselor(user):
    try:
        return user.profile.role == "موجه طلابي"
    except Profile.DoesNotExist:
        return False


def _can_view(user, ref: Referral):
    # يستطيع العرض: الأدمِن + المنشئ + المكلّف الحالي
    return (
        user.is_staff
        or user == ref.created_by
        or (ref.assignee_id and user.id == ref.assignee_id)
    )


def _can_assign(user, ref: Referral):
    # السماح بتحويل الإحالة أيضًا للموجّه الطلابي
    if user.is_staff or user == ref.created_by:
        return True
    try:
        return user.profile.role == "موجه طلابي"
    except Profile.DoesNotExist:
        return False


def _value_display(val):
    if isinstance(val, bool):
        return "نعم" if val else "لا"
    if val in (None, "", [], {}):
        return "—"
    return str(val)


def _intake_display_list(intake: CounselorIntake, form: CounselorIntakeForm):
    """
    يُرجع قائمة [(label, human_value)] جاهزة للعرض في القالب،
    مع احترام الحقول ذات الاختيارات (choices) لعرض نص الاختيار.
    """
    items = []
    for name, field in form.fields.items():
        label = field.label or name
        # إن كان للخاصية get_FOO_display استخدمها
        getter_name = f"get_{name}_display"
        if hasattr(intake, getter_name):
            try:
                val = getattr(intake, getter_name)()
            except Exception:
                val = getattr(intake, name, None)
        else:
            val = getattr(intake, name, None)
        items.append((label, _value_display(val)))
    return items


# ------------------ القائمة مع الفلاتر والعدادات ------------------
@login_required
def list_referrals(request: HttpRequest):
    scope = request.GET.get("scope", "all")

    sent_qs = Referral.objects.filter(created_by=request.user)
    inbox_qs = Referral.objects.filter(assignee=request.user)

    if scope == "sent":
        items = sent_qs
    elif scope == "inbox":
        items = inbox_qs
    else:
        items = Referral.objects.filter(
            Q(created_by=request.user) | Q(assignee=request.user)
        )

    items = items.order_by("-created_at")
    counts = {
        "all": Referral.objects.filter(
            Q(created_by=request.user) | Q(assignee=request.user)
        ).count(),
        "sent": sent_qs.count(),
        "inbox": inbox_qs.count(),
    }

    return render(
        request,
        "referrals/index.html",
        {"items": items, "counts": counts, "scope": scope},
    )


# ------------------ إنشاء إحالة ------------------
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

        # تحويل تلقائي لأول موجّه طلابي نشِط إن وُجد
        counselor = User.objects.filter(
            is_active=True, profile__role="موجه طلابي"
        ).first()
        if counselor:
            ref.assignee = counselor
            ref.status = "UNDER_REVIEW"
            ref.save(update_fields=["assignee", "status"])
            Action.objects.create(
                referral=ref,
                author=request.user,
                kind="NOTE",
                content=f"تحويل تلقائي إلى الموجّه الطلابي: {counselor.username}",
            )

        messages.success(request, _("تم إنشاء الإحالة بنجاح."))
        return redirect("referrals:detail", pk=ref.pk)

    return render(request, "referrals/new.html", _ctx())


# ------------------ تفاصيل الإحالة ------------------
@login_required
def detail_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه الإحالة.")

    assignable = (
        User.objects.filter(is_active=True)
        .exclude(id=request.user.id)
        .order_by("username")
    )
    actions = (
        Action.objects.filter(referral=ref)
        .select_related("author")
        .prefetch_related("files")
        .order_by("created_at")
    )
    is_counselor = _is_counselor(request.user)

    # تجهيز ملخص نموذج الموجّه ليظهر للمكلّف الحالي أو الموجّه/الأدمِن
    intake = CounselorIntake.objects.filter(referral=ref).first()
    intake_display = []
    can_view_intake = False
    if intake:
        can_view_intake = (
            request.user.is_staff
            or is_counselor
            or (ref.assignee_id and request.user.id == ref.assignee_id)
        )
        if can_view_intake:
            intake_form = CounselorIntakeForm(instance=intake)
            intake_display = _intake_display_list(intake, intake_form)

    return render(
        request,
        "referrals/detail.html",
        {
            "r": ref,
            "assignable": assignable,
            "actions": actions,
            "is_counselor": is_counselor,
            "intake": intake,
            "can_view_intake": can_view_intake,
            "intake_display": intake_display,
        },
    )


# ------------------ تحويل الإحالة ------------------
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

    # عند التحويل من الموجّه: سجّل ملاحظة تُفيد بأن ملخص النموذج متاح للمكلَّف
    note = "تحويل إلى {}.".format(new_assignee.username)
    if _is_counselor(request.user) and CounselorIntake.objects.filter(referral=ref).exists():
        note += " ملاحظة: هذه الإحالة تحتوي على ملخص لنموذج الموجّه وسيظهر للمكلّف."

    Action.objects.create(referral=ref, author=request.user, kind="NOTE", content=note)

    messages.success(request, f"تم تحويل الإحالة إلى المستخدم: {new_assignee.username}")
    return redirect("referrals:detail", pk=ref.pk)


# ------------------ رد على الإحالة ------------------
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

    act = Action.objects.create(
        referral=ref, author=request.user, kind="REPLY", content=content
    )
    for f in checked:
        ActionAttachment.objects.create(action=act, file=f, uploaded_by=request.user)

    if ref.status == "NEW":
        ref.status = "UNDER_REVIEW"
        ref.save()

    messages.success(request, "تم إرسال الرد.")
    return redirect("referrals:detail", pk=ref.pk)


# ------------------ إغلاق الإحالة ------------------
@login_required
@require_http_methods(["POST"])
def close_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية إغلاق هذه الإحالة.")

    if not Action.objects.filter(referral=ref).exists():
        messages.error(
            request, "لا يمكن إغلاق الإحالة قبل اتخاذ إجراء (رد/ملاحظة/تحويل)."
        )
        return redirect("referrals:detail", pk=ref.pk)

    ref.status = "CLOSED"
    ref.save()
    Action.objects.create(
        referral=ref, author=request.user, kind="DECISION", content="تم إغلاق الإحالة."
    )
    messages.success(request, "تم إغلاق الإحالة.")
    return redirect("referrals:detail", pk=ref.pk)


# ------------------ شاشة الموجّه السرّية (التعبئة/التعديل) ------------------
@login_required
@require_http_methods(["GET", "POST"])
def counselor_intake_view(request, pk: int):
    """هذه الصفحة للموجّه الطلابي فقط لتعبئة/تحديث النموذج."""
    ref = get_object_or_404(Referral, pk=pk)
    if not _is_counselor(request.user):
        return HttpResponseForbidden("هذه الصفحة للموجّه الطلابي فقط.")

    intake, _created = CounselorIntake.objects.get_or_create(referral=ref)

    if request.method == "POST":
        form = CounselorIntakeForm(request.POST, instance=intake)
        if form.is_valid():
            form.save()
            messages.success(request, "تم حفظ نموذج الموجّه.")
            return redirect("referrals:detail", pk=ref.pk)
    else:
        form = CounselorIntakeForm(instance=intake)

    return render(request, "referrals/counselor_form.html", {"r": ref, "form": form})
