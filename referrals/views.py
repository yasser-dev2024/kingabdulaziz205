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

def _can_view(user, ref: Referral):
    return user.is_staff or user == ref.created_by or (ref.assignee and user == ref.assignee)

def _is_counselor(user):
    try:
        return user.profile.role == "موجه طلابي"
    except Profile.DoesNotExist:
        return False

def _can_assign(user, ref: Referral):
    return (user.is_staff or user == ref.created_by or _is_counselor(user) or (ref.assignee_id == user.id))

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
    # يدعم حقول choices عبر get_FOO_display
    disp = None
    try:
        disp = getattr(obj, f"get_{field}_display")()
        if disp: return disp
    except Exception:
        pass
    return getattr(obj, field, None)

def _mk_pair(obj, field):
    val = _get_value(obj, field)
    if val in (None, "", False):  # نتجاهل الفارغ و False
        return None
    return (_get_label(obj, field), _display(val))

def _counselor_summary_struct(intake):
    """يُرجع List من أقسام: كل قسم dict فيه title و items [(label, value)]."""
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
    sent_qs = Referral.objects.filter(created_by=request.user)
    inbox_qs = Referral.objects.filter(assignee=request.user)
    if scope == "sent":
        items_qs = sent_qs
    elif scope == "inbox":
        items_qs = inbox_qs
    else:
        items_qs = Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user))
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
    counts = {"all": Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user)).count(),
              "sent": sent_qs.count(), "inbox": inbox_qs.count()}
    return render(request, "referrals/index.html", {"items": items, "groups": groups, "counts": counts, "scope": scope})

# ——— إنشاء إحالة ———
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

        counselor = User.objects.filter(is_active=True, profile__role="موجه طلابي").first()
        if counselor:
            ref.assignee = counselor
            ref.status = "UNDER_REVIEW"
            ref.save(update_fields=["assignee", "status"])
            Action.objects.create(referral=ref, author=request.user, kind="NOTE",
                                  content=f"تحويل تلقائي إلى الموجّه الطلابي: {counselor.username}")

        messages.success(request, _("تم إنشاء الإحالة بنجاح."))
        return redirect("referrals:detail", pk=ref.pk)

    return render(request, "referrals/new.html", _ctx())

# ——— تفاصيل ———
@login_required
def detail_referral(request, pk: int):
    ref = get_object_or_404(Referral, pk=pk)
    if not _can_view(request.user, ref):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه الإحالة.")
    _ensure_student_key(ref)

    assignable = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by("username")
    actions = (Action.objects.filter(referral=ref).select_related("author").prefetch_related("files").order_by("created_at"))
    is_counselor = _is_counselor(request.user)

    same_student_qs = Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user)).exclude(pk=ref.pk).order_by("-created_at")
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
        # 👇 هنا التعديل: كل من يملك صلاحية عرض الإحالة يرى الملخص
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

    if ref.status == "NEW":
        ref.status = "UNDER_REVIEW"
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
    if not Action.objects.filter(referral=ref).exists():
        messages.error(request, "لا يمكن إغلاق الإحالة قبل اتخاذ إجراء (رد/ملاحظة/تحويل).")
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
    if not (_is_counselor(request.user) or request.user.is_staff or ref.assignee_id == request.user.id):
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

    # 1) قالب إن وُجد
    try:
        tmpl = loader.get_template("referrals/counselor_form.html")
        return HttpResponse(tmpl.render(context, request))
    except TemplateDoesNotExist:
        pass

    # 2) Fallback Inline — لا يعتمد على أي ملف (كامل)
    inline_tmpl = engines["django"].from_string("""
<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>نموذج بيانات الموجّه</title>
<style>
  body{font-family:system-ui,Segoe UI,Roboto,Arial;background:#f6f7fb;margin:0}
  .container{max-width:1100px;margin:28px auto;padding:0 12px}
  .card{background:#fff;border-radius:18px;box-shadow:0 10px 28px rgba(2,6,23,.07);overflow:hidden}
  .header{display:flex;justify-content:space-between;align-items:center;padding:16px 18px;background:linear-gradient(90deg,#06b6d4,#6366f1);color:#fff}
  .section{padding:16px 18px}
  .grid{display:grid;gap:12px}
  .grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}
  .grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}
  @media(max-width:900px){.grid-2,.grid-3{grid-template-columns:1fr}}
  .h6{margin:0 0 8px 0;font-size:15px;color:#0f172a}
  .box{border:1px solid #e5e7eb;border-radius:12px;padding:12px;background:#fafafa}
  label{display:block;margin-bottom:6px;font-weight:600;color:#334155;font-size:14px}
  input[type="text"],input[type="date"],select,textarea{width:100%;padding:10px 12px;border:1px solid #e5e7eb;border-radius:10px;background:#fff}
  textarea{min-height:90px}
  .actions{display:flex;gap:10px;margin-top:12px}
  .btn{padding:10px 14px;border-radius:10px;border:0;cursor:pointer}
  .btn-primary{background:#2563eb;color:#fff}
  .btn-light{background:#eef2ff;color:#1f2937;text-decoration:none}
  .badge{background:#eef2ff;color:#1f2937;border-radius:9999px;padding:6px 10px;font-size:12px}
  .hr{height:1px;background:#e5e7eb;margin:10px 0}
</style></head><body>
<div class="container"><div class="card">
  <div class="header">
    <div style="display:flex;align-items:center;gap:8px">
      <span class="badge">إحالة #{{ r.pk }}</span>
      <strong>نموذج بيانات الموجّه</strong>
    </div>
    <a href="{% url 'referrals:detail' r.pk %}" class="btn btn-light">عودة للتفاصيل</a>
  </div>

  <form method="post" novalidate>
  {% csrf_token %}

  <div class="section">
    <div class="grid grid-3">
      <div><label>اسم الموجّه</label>{{ form.counselor_name }}</div>
      <div><label>تاريخ المتابعة</label>{{ form.follow_up_date }}</div>
      <div></div>
    </div>
  </div>

  <div class="section box">
    <h4 class="h6">المعلومات الاجتماعية/التعليمية</h4>
    <div class="grid grid-3">
      <div><label>{{ form.father_alive.label }}</label>{{ form.father_alive }}</div>
      <div><label>{{ form.mother_alive.label }}</label>{{ form.mother_alive }}</div>
      <div><label>{{ form.parents_status.label }}</label>{{ form.parents_status }}</div>

      <div><label>{{ form.siblings_count.label }}</label>{{ form.siblings_count }}</div>
      <div><label>{{ form.birth_order.label }}</label>{{ form.birth_order }}</div>
      <div></div>

      <div><label>{{ form.father_education.label }}</label>{{ form.father_education }}</div>
      <div><label>{{ form.mother_education.label }}</label>{{ form.mother_education }}</div>
      <div></div>
    </div>
  </div>

  <div class="section box">
    <h4 class="h6">المعلومات الاقتصادية</h4>
    <div class="grid grid-3">
      <div><label>{{ form.father_job.label }}</label>{{ form.father_job }}</div>
      <div><label>{{ form.mother_job.label }}</label>{{ form.mother_job }}</div>
      <div><label>{{ form.family_income.label }}</label>{{ form.family_income }}</div>

      <div><label>{{ form.receives_social_support.label }}</label>{{ form.receives_social_support }}</div>
      <div><label>{{ form.house_ownership.label }}</label>{{ form.house_ownership }}</div>
      <div><label>{{ form.gets_everything_easily.label }}</label>{{ form.gets_everything_easily }}</div>

      <div><label>{{ form.house_type.label }}</label>{{ form.house_type }}</div>
      <div><label>{{ form.house_type_other.label }}</label>{{ form.house_type_other }}</div>
      <div></div>
    </div>
  </div>

  <div class="section box">
    <h4 class="h6">المعلومات الصحية</h4>
    <div class="grid grid-3">
      <div><label>{{ form.disease_heart.label }}</label>{{ form.disease_heart }}</div>
      <div><label>{{ form.disease_pressure.label }}</label>{{ form.disease_pressure }}</div>
      <div><label>{{ form.disease_kidney.label }}</label>{{ form.disease_kidney }}</div>
      <div><label>{{ form.disease_sleep.label }}</label>{{ form.disease_sleep }}</div>
      <div><label>{{ form.disease_vision.label }}</label>{{ form.disease_vision }}</div>
      <div><label>{{ form.disease_other.label }}</label>{{ form.disease_other }}</div>
    </div>
    <div class="hr"></div>
    <div class="grid grid-3">
      <div><label>{{ form.cond_asthma.label }}</label>{{ form.cond_asthma }}</div>
      <div><label>{{ form.cond_diabetes.label }}</label>{{ form.cond_diabetes }}</div>
      <div><label>{{ form.cond_anemia.label }}</label>{{ form.cond_anemia }}</div>
      <div><label>{{ form.cond_tonsils.label }}</label>{{ form.cond_tonsils }}</div>
      <div><label>{{ form.cond_seizures.label }}</label>{{ form.cond_seizures }}</div>
      <div><label>{{ form.cond_hearing.label }}</label>{{ form.cond_hearing }}</div>
      <div><label>{{ form.cond_allergy.label }}</label>{{ form.cond_allergy }}</div>
      <div><label>{{ form.cond_rheumatism.label }}</label>{{ form.cond_rheumatism }}</div>
      <div><label>{{ form.cond_disability.label }}</label>{{ form.cond_disability }}</div>
    </div>
  </div>

  <div class="section box">
    <h4 class="h6">المعلومات عن السلك العسكري</h4>
    <div class="grid grid-3">
      <div><label>{{ form.father_in_military.label }}</label>{{ form.father_in_military }}</div>
      <div><label>{{ form.father_served_southern.label }}</label>{{ form.father_served_southern }}</div>
      <div><label>{{ form.father_is_martyr_south.label }}</label>{{ form.father_is_martyr_south }}</div>
    </div>
  </div>

  <div class="section box">
    <h4 class="h6">ملاحظات وتوصيات</h4>
    <div class="grid grid-2">
      <div><label>{{ form.student_behavior.label }}</label>{{ form.student_behavior }}</div>
      <div><label>{{ form.previous_interventions.label }}</label>{{ form.previous_interventions }}</div>
      <div style="grid-column:1/-1"><label>{{ form.recommendations.label }}</label>{{ form.recommendations }}</div>
    </div>
  </div>

  <div class="section">
    <div class="actions">
      <a href="{% url 'referrals:detail' r.pk %}" class="btn btn-light">إلغاء</a>
      <button type="submit" class="btn btn-primary">حفظ</button>
    </div>
  </div>

  </form>
</div></div>
</body></html>
    """)
    return HttpResponse(inline_tmpl.render(context, request))

# ——— ملف الطالب ———
@login_required
def student_file(request, key: str):
    visible_qs = Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user)).order_by("-created_at")
    visible = list(visible_qs)
    for r in visible: _ensure_student_key(r)
    items = [r for r in visible if getattr(r, "student_key", "") == key]
    student_name = items[0].student_name if items else ""

    # ملخص لكل إحالة فيها Intake
    intake_map = {}
    if HAS_COUNSELOR:
        for r in items:
            try:
                intake = getattr(r, "counselor_intake", None)
                if intake:
                    intake_map[r.pk] = _counselor_summary_struct(intake)
            except Exception:
                pass

    # أيضًا نجهّز خاصية مباشرة لكل r لسهولة الإدراج في القوالب
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
