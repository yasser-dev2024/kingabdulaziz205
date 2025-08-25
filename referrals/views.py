from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext as _
from django.http import HttpResponseForbidden, HttpRequest, HttpResponse
from django.db.models import Q
from django.template import loader, TemplateDoesNotExist, engines
import unicodedata, re

from accounts.models import Profile
from .models import Referral, Attachment, Action, ActionAttachment
from .utils import make_student_key

# ===== تفعيل نموذج الموجّه: من models.py أو counselor_models.py =====
HAS_COUNSELOR = False
CounselorIntake = None
CounselorIntakeForm = None
try:
    from .models import CounselorIntake as _CI
    from .forms import CounselorIntakeForm as _CIF
    CounselorIntake, CounselorIntakeForm, HAS_COUNSELOR = _CI, _CIF, True
except Exception:
    try:
        from .counselor_models import CounselorIntake as _CI
        from .forms import CounselorIntakeForm as _CIF
        CounselorIntake, CounselorIntakeForm, HAS_COUNSELOR = _CI, _CIF, True
    except Exception:
        HAS_COUNSELOR = False

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_FILES = 5

# ——— helpers ———
def _ctx(form=None, errors=None):
    return {"form": form or {}, "errors": errors or {}, "grades": Referral.GRADE_CHOICES, "types": Referral.TYPE_CHOICES}

def _is_manager(user):
    try:
        return bool(user.is_staff or (getattr(user, "profile", None) and user.profile.role == "مدير المدرسة"))
    except Profile.DoesNotExist:
        return bool(user.is_staff)

def _can_view(user, ref: Referral):
    return _is_manager(user) or user == ref.created_by or (ref.assignee and user == ref.assignee)

def _is_counselor(user):
    try:
        return user.profile.role == "موجه طلابي"
    except Profile.DoesNotExist:
        return False

def _can_assign(user, ref: Referral):
    return (_is_manager(user) or user.is_staff or user == ref.created_by or _is_counselor(user) or (ref.assignee_id == user.id))

def _ensure_student_key(ref: Referral):
    try:
        has_key_field = hasattr(ref, "student_key")
    except Exception:
        has_key_field = False
    if not has_key_field:
        return
    try:
        if getattr(ref, "student_key", ""):
            return
        civil = (getattr(ref, "student_civil_id", None) or "")[:64]
        new_key = make_student_key(getattr(ref, "student_name", ""), civil)
        if new_key:
            ref.student_key = new_key
            ref.save(update_fields=["student_key"])
    except Exception:
        pass

def _display(v):
    if v is True: return "نعم"
    if v is False or v == "False": return "لا"
    return v

def _get_label(obj, field):
    try:
        return obj._meta.get_field(field).verbose_name
    except Exception:
        return field

def _get_value(obj, field):
    disp = None
    try:
        disp = getattr(obj, f"get_{field}_display")()
        if disp: return disp
    except Exception:
        pass
    return getattr(obj, field, None)

def _mk_pair(obj, field):
    val = _get_value(obj, field)
    if val in (None, "", False):
        return None
    return (_get_label(obj, field), _display(val))

def _counselor_summary_struct(intake):
    if not intake:
        return []
    sec_social = [
        _mk_pair(intake, "father_alive"),
        _mk_pair(intake, "mother_alive"),
        _mk_pair(intake, "parents_status"),
        _mk_pair(intake, "siblings_count"),
        _mk_pair(intake, "birth_order"),
        _mk_pair(intake, "father_education"),
        _mk_pair(intake, "mother_education"),
    ]
    sec_economic = [
        _mk_pair(intake, "father_job"),
        _mk_pair(intake, "mother_job"),
        _mk_pair(intake, "family_income"),
        _mk_pair(intake, "receives_social_support"),
        _mk_pair(intake, "house_ownership"),
        _mk_pair(intake, "house_type"),
        _mk_pair(intake, "house_type_other"),
        _mk_pair(intake, "gets_everything_easily"),
    ]
    sec_health_major = [
        _mk_pair(intake, "disease_heart"),
        _mk_pair(intake, "disease_pressure"),
        _mk_pair(intake, "disease_kidney"),
        _mk_pair(intake, "disease_sleep"),
        _mk_pair(intake, "disease_vision"),
        _mk_pair(intake, "disease_other"),
    ]
    sec_health_minor = [
        _mk_pair(intake, "cond_asthma"),
        _mk_pair(intake, "cond_diabetes"),
        _mk_pair(intake, "cond_anemia"),
        _mk_pair(intake, "cond_tonsils"),
        _mk_pair(intake, "cond_seizures"),
        _mk_pair(intake, "cond_hearing"),
        _mk_pair(intake, "cond_allergy"),
        _mk_pair(intake, "cond_rheumatism"),
        _mk_pair(intake, "cond_disability"),
    ]
    sec_military = [
        _mk_pair(intake, "father_in_military"),
        _mk_pair(intake, "father_served_southern"),
        _mk_pair(intake, "father_is_martyr_south"),
    ]
    sec_notes = [
        _mk_pair(intake, "student_behavior"),
        _mk_pair(intake, "previous_interventions"),
        _mk_pair(intake, "recommendations"),
        _mk_pair(intake, "follow_up_date"),
    ]
    def pack(title, items):
        items = [x for x in items if x]
        return {"title": title, "items": items} if items else None
    groups = [
        pack("المعلومات الاجتماعية/التعليمية", sec_social),
        pack("المعلومات الاقتصادية", sec_economic),
        pack("المعلومات الصحية", sec_health_major + sec_health_minor),
        pack("المعلومات عن السلك العسكري", sec_military),
        pack("ملاحظات وتوصيات", sec_notes),
    ]
    return [g for g in groups if g]

# ——— القائمة ———
@login_required
def list_referrals(request: HttpRequest):
    scope = request.GET.get("scope", "all")

    if _is_manager(request.user):
        sent_qs = Referral.objects.all()
        inbox_qs = Referral.objects.all()
        base_qs = Referral.objects.all()
    else:
        sent_qs = Referral.objects.filter(created_by=request.user)
        inbox_qs = Referral.objects.filter(assignee=request.user)
        base_qs = Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user))

    if scope == "sent":
        items_qs = sent_qs
    elif scope == "inbox":
        items_qs = inbox_qs
    else:
        items_qs = base_qs

    items_qs = items_qs.select_related("created_by", "assignee").order_by("-created_at")
    items = list(items_qs)
    for r in items: _ensure_student_key(r)

    groups_map = {}
    for r in items:
        key = getattr(r, "student_key", "") or f"ref-{r.pk}"
        g = groups_map.get(key)
        if not g:
            g = {"key": getattr(r, "student_key", "") or "", "student_name": r.student_name, "latest": r.created_at, "referrals": []}
            groups_map[key] = g
        g["referrals"].append(r)
        if r.created_at > g["latest"]: g["latest"] = r.created_at
        if r.created_at >= g["latest"]: g["student_name"] = r.student_name
    groups = sorted(groups_map.values(), key=lambda x: x["latest"], reverse=True)

    counts = {
        "all": base_qs.count(),
        "sent": sent_qs.count(),
        "inbox": inbox_qs.count()
    }
    return render(request, "referrals/index.html", {"items": items, "groups": groups, "counts": counts, "scope": scope})

# ——— إنشاء إحالة ———
@login_required
@require_http_methods(["GET", "POST"])
def create_referral(request):
    # قائمة المستخدمين لاختيار "إرسال الإحالة إلى"
    users_qs = User.objects.filter(is_active=True).order_by("username")

    if request.method == "POST":
        student_name = (request.POST.get("student_name") or "").strip()
        grade = (request.POST.get("grade") or "").strip()
        referral_type = (request.POST.get("referral_type") or "").strip()
        details = (request.POST.get("details") or "").strip()
        student_civil_id = (request.POST.get("student_civil_id") or "").strip()
        assignee_raw = (request.POST.get("assignee") or "").strip()
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

        # التحقق من المرسل إليه إذا تم اختياره
        assignee_user = None
        if assignee_raw:
            try:
                assignee_user = User.objects.get(pk=int(assignee_raw), is_active=True)
            except Exception:
                errors["assignee"] = "المستخدم المحدد غير متاح."

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
            ctx = {**_ctx(request.POST, errors), "users": users_qs, "selected_assignee": assignee_raw}
            return render(request, "referrals/new.html", ctx)

        ref = Referral.objects.create(
            student_name=student_name, grade=grade, referral_type=referral_type,
            details=details, created_by=request.user, status="UNDER_REVIEW",
        )

        updated_fields = []
        if hasattr(ref, "student_civil_id"):
            ref.student_civil_id = student_civil_id or None
            updated_fields.append("student_civil_id")
        if hasattr(ref, "student_key"):
            ref.student_key = make_student_key(student_name, student_civil_id)
            updated_fields.append("student_key")
        if updated_fields:
            try: ref.save(update_fields=updated_fields)
            except Exception: pass

        for f in checked_files:
            Attachment.objects.create(referral=ref, file=f, uploaded_by=request.user)

        # إن اختار المستخدم مرسلاً إليه نعيّنه مباشرة، وإلا نستخدم السلوك السابق (الموجّه إن وُجد)
        if assignee_user:
            ref.assignee = assignee_user
            ref.status = "UNDER_REVIEW"
            ref.save(update_fields=["assignee", "status"])
            Action.objects.create(referral=ref, author=request.user, kind="NOTE",
                                  content=f"تحويل تلقائي إلى {assignee_user.username}")
        else:
            counselor = User.objects.filter(is_active=True, profile__role="موجه طلابي").first()
            if counselor:
                ref.assignee = counselor
                ref.status = "UNDER_REVIEW"
                ref.save(update_fields=["assignee", "status"])
                Action.objects.create(referral=ref, author=request.user, kind="NOTE",
                                      content=f"تحويل تلقائي إلى الموجّه الطلابي: {counselor.username}")

        messages.success(request, _("تم إنشاء الإحالة بنجاح."))
        return redirect("referrals:detail", pk=ref.pk)

    # GET
    return render(request, "referrals/new.html", {**_ctx(), "users": users_qs, "selected_assignee": ""})

# ——— تفاصيل ———
@login_required
def detail_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه الإحالة.")
    _ensure_student_key(ref)

    # عند فتح الإحالة من المكلّف تُعتبر مفتوحة (لأجل الوسم الأخضر بعد الرد)
    if ref.assignee_id == request.user.id and not getattr(ref, "is_opened_by_assignee", False):
        try:
            ref.is_opened_by_assignee = True
            ref.save(update_fields=["is_opened_by_assignee"])
        except Exception:
            pass

    assignable = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by("username")
    actions = (Action.objects.filter(referral=ref).select_related("author").prefetch_related("files").order_by("created_at"))
    is_counselor = _is_counselor(request.user)

    base_same_qs = Referral.objects.exclude(pk=ref.pk).order_by("-created_at")
    if _is_manager(request.user):
        same_student_qs = base_same_qs
    else:
        same_student_qs = base_same_qs.filter(Q(created_by=request.user) | Q(assignee=request.user))

    same_student = []
    for r in same_student_qs:
        _ensure_student_key(r)
        if getattr(ref, "student_key", "") and getattr(r, "student_key", "") and r.student_key == ref.student_key:
            same_student.append(r)
        if len(same_student) >= 10: break

    files = getattr(ref, "attachments", Attachment.objects.none()).all()

    counselor_summary = []
    can_view_counselor_summary = False
    if HAS_COUNSELOR:
        try:
            intake = getattr(ref, "counselor_intake", None)
        except Exception:
            intake = None
        can_view_counselor_summary = _can_view(request.user, ref)
        if intake and can_view_counselor_summary:
            counselor_summary = _counselor_summary_struct(intake)

    return render(request, "referrals/detail.html", {
        "r": ref, "assignable": assignable, "actions": actions,
        "is_counselor": is_counselor, "same_student": same_student,
        "files": files, "HAS_COUNSELOR": HAS_COUNSELOR,
        "counselor_summary": counselor_summary,
        "can_view_counselor_summary": can_view_counselor_summary,
    })

# ——— تحويل ———
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

    Action.objects.create(referral=ref, author=request.user, kind="NOTE",
                          content=f"تحويل إلى {new_assignee.username}")

    if HAS_COUNSELOR and (new_assignee == request.user):
        messages.info(request, "تم تحويل الإحالة لك — افتح نموذج بيانات الموجّه.")
        return redirect("referrals:counselor", pk=ref.pk)

    messages.success(request, f"تم تحويل الإحالة إلى المستخدم: {new_assignee.username}")
    return redirect("referrals:detail", pk=ref.pk)

# ——— رد ———
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

    # وسم الرد ليتحول لون البطاقة للأخضر بعد الفتح
    if not getattr(ref, "has_reply", False):
        try:
            ref.has_reply = True
        except Exception:
            pass
    if ref.status == "NEW":
        ref.status = "UNDER_REVIEW"
    try:
        ref.save(update_fields=["has_reply", "status"])
    except Exception:
        ref.save()

    messages.success(request, "تم إرسال الرد.")
    return redirect("referrals:detail", pk=ref.pk)

# ——— إغلاق ———
@login_required
@require_http_methods(["POST"])
def close_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية إغلاق هذه الإحالة.")

    # يمنع الإغلاق قبل وجود "رد" أو توصية في نموذج الموجه (إن وُجد)
    has_valid = Action.objects.filter(referral=ref, kind="REPLY").exists()
    if not has_valid and HAS_COUNSELOR:
        try:
            intake = getattr(ref, "counselor_intake", None)
            if intake and getattr(intake, "recommendations", "").strip():
                has_valid = True
        except Exception:
            pass

    if not has_valid:
        messages.error(request, "لا يمكن إغلاق الإحالة قبل وضع رد أو توصية.")
        return redirect("referrals:detail", pk=ref.pk)

    ref.status = "CLOSED"
    ref.save()
    Action.objects.create(referral=ref, author=request.user, kind="DECISION", content="تم إغلاق الإحالة.")
    messages.success(request, "تم إغلاق الإحالة.")
    return redirect("referrals:detail", pk=ref.pk)

# ——— شاشة الموجّه ———
@login_required
@require_http_methods(["GET", "POST"])
def counselor_intake_view(request, pk: int):
    if not HAS_COUNSELOR:
        return HttpResponseForbidden("هذه الصفحة غير مفعّلة (نموذج الموجّه غير مُثبت).")
    ref = get_object_or_404(Referral, pk=pk)
    if not (_is_counselor(request.user) or _is_manager(request.user) or request.user.is_staff or ref.assignee_id == request.user.id):
        return HttpResponseForbidden("هذه الصفحة للموجّه/المشرف/المكلّف فقط.")

    intake, _ = CounselorIntake.objects.get_or_create(referral=ref, defaults={
        "created_by": request.user, "updated_by": request.user
    })

    if request.method == "POST":
        form = CounselorIntakeForm(request.POST, instance=intake)
        if form.is_valid():
            obj = form.save(commit=False)
            if hasattr(obj, "updated_by"):
                obj.updated_by = request.user
            obj.save()
            messages.success(request, "تم حفظ نموذج الموجّه.")
            return redirect("referrals:detail", pk=ref.pk)
    else:
        form = CounselorIntakeForm(instance=intake)

    context = {"r": ref, "form": form}

    try:
        tmpl = loader.get_template("referrals/counselor_form.html")
        return HttpResponse(tmpl.render(context, request))
    except TemplateDoesNotExist:
        pass

    inline_tmpl = engines["django"].from_string("""<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>نموذج بيانات الموجّه</title>
</head><body>
<form method="post">{% csrf_token %}{{ form.as_p }}<button type="submit">حفظ</button></form>
</body></html>""")
    return HttpResponse(inline_tmpl.render(context, request))

# ——— ملف الطالب ———
@login_required
def student_file(request, key: str):
    if _is_manager(request.user):
        visible_qs = Referral.objects.all().order_by("-created_at")
    else:
        visible_qs = Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user)).order_by("-created_at")

    visible = list(visible_qs)
    for r in visible: _ensure_student_key(r)
    items = [r for r in visible if getattr(r, "student_key", "") == key]
    student_name = items[0].student_name if items else ""

    intake_map = {}
    if HAS_COUNSELOR:
        for r in items:
            try:
                intake = getattr(r, "counselor_intake", None)
                if intake:
                    intake_map[r.pk] = _counselor_summary_struct(intake)
            except Exception:
                pass

    if HAS_COUNSELOR:
        for r in items:
            try:
                intake = getattr(r, "counselor_intake", None)
                r.counselor_summary = _counselor_summary_struct(intake) if intake else []
            except Exception:
                r.counselor_summary = []

    return render(request, "referrals/student_file.html", {
        "student_name": student_name, "items": items, "key": key,
        "intake_map": intake_map, "HAS_COUNSELOR": HAS_COUNSELOR,
    })
