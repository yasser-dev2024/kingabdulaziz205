from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import os

# ---------- أدوات رفع الملفات ----------
def referral_upload_path(instance, filename):
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    return f"referrals/{instance.referral_id}/{safe}{ext.lower()}"

def action_upload_path(instance, filename):
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    # يوفّر Django الحقل action_id (المفتاح الأجنبي كعدد)
    action_id = getattr(instance, "action_id", None) or "tmp"
    return f"referrals/actions/{action_id}/{safe}{ext.lower()}"

def generate_reference():
    return "R-" + timezone.now().strftime("%Y") + "-" + uuid.uuid4().hex[:6].upper()


# ---------- الإحالة ----------
class Referral(models.Model):
    STATUS_CHOICES = [
        ("NEW", "جديدة"),
        ("UNDER_REVIEW", "قيد المراجعة"),
        ("SENT_TO_DEPUTY", "محالة لوكيل"),
        ("CLOSED", "مغلقة"),
    ]
    TYPE_CHOICES = [
        ("behavior", "سلوكي"),
        ("academic", "تحصيلي"),
        ("health", "صحي"),
        ("other", "أخرى"),
    ]
    GRADE_CHOICES = [(str(i), f"الصف {i}") for i in range(1, 13)]

    reference = models.CharField(max_length=20, default=generate_reference, unique=True, editable=False)
    student_name = models.CharField(max_length=120)
    grade = models.CharField(max_length=2, choices=GRADE_CHOICES)
    referral_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="NEW")

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_referrals")
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_referrals")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.reference} - {self.student_name}"

    @property
    def referral_id(self):
        return self.pk or "tmp"


class Attachment(models.Model):
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=referral_upload_path)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"مرفق {self.referral.reference}"


# ---------- إجراءات/ردود ----------
class Action(models.Model):
    KIND_CHOICES = [
        ("REPLY", "رد"),
        ("NOTE", "ملاحظة"),
        ("DECISION", "قرار"),
    ]
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name="actions")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default="REPLY")
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_kind_display()} - {self.referral.reference}"


class ActionAttachment(models.Model):
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=action_upload_path)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"مرفق إجراء {self.action_id}"


# ---------- نموذج سرّي للموجّه الطلابي ----------
class CounselorIntake(models.Model):
    """نموذج بيانات سرّي للموجّه الطلابي فقط، مرتبط بإحالة واحدة."""
    referral = models.OneToOneField(Referral, on_delete=models.CASCADE, related_name="counselor_intake")

    # اجتماعية/تعليمية
    father_alive = models.BooleanField(default=True, verbose_name="هل الأب على قيد الحياة؟")
    mother_alive = models.BooleanField(default=True, verbose_name="هل الأم على قيد الحياة؟")
    parents_status = models.CharField(
        max_length=20,
        choices=[("مستقران", "مستقران"), ("منفصلان", "منفصلان")],
        default="مستقران",
        verbose_name="الحالة الاجتماعية للوالدين",
    )
    siblings_count = models.PositiveIntegerField(default=0, verbose_name="عدد الإخوة والأخوات")
    child_order = models.CharField(max_length=50, blank=True, verbose_name="ترتيب الطالب بين إخوته")
    father_edu = models.CharField(
        max_length=20,
        choices=[("أمي","أمي"), ("يقرأ ويكتب","يقرأ ويكتب"), ("الابتدائية","الابتدائية"),
                 ("المتوسطة","المتوسطة"), ("الثانوية","الثانوية"), ("بكالوريوس","بكالوريوس"),
                 ("ماجستير","ماجستير"), ("دكتوراه","دكتوراه")],
        default="الثانوية", verbose_name="المستوى التعليمي للأب"
    )
    mother_edu = models.CharField(
        max_length=20,
        choices=[("أمي","أمي"), ("يقرأ ويكتب","يقرأ ويكتب"), ("الابتدائية","الابتدائية"),
                 ("المتوسطة","المتوسطة"), ("الثانوية","الثانوية"), ("بكالوريوس","بكالوريوس"),
                 ("ماجستير","ماجستير"), ("دكتوراه","دكتوراه")],
        default="الثانوية", verbose_name="المستوى التعليمي للأم"
    )

    # اقتصادية
    father_job = models.CharField(max_length=120, blank=True, verbose_name="مهنة الأب")
    mother_job = models.CharField(max_length=120, blank=True, verbose_name="مهنة الأم")
    family_income = models.CharField(
        max_length=20,
        choices=[("أقل من 3000","أقل من (٣٠٠٠) ريال"),
                 ("3000-6000","من (٣٠٠٠) إلى (٦٠٠٠) ريال"),
                 ("6000-10000","من (٦٠٠٠) إلى (١٠٠٠٠) ريال"),
                 ("أكثر من 10000","أكثر من (١٠٠٠٠) ريال")],
        default="3000-6000", verbose_name="دخل الأسرة"
    )
    has_insurance = models.BooleanField(default=False, verbose_name="هل يتم صرف ضمان اجتماعي لكم؟")
    housing_type = models.CharField(
        max_length=20,
        choices=[("شقة","شقة"), ("بيت شعبي","بيت شعبي"), ("دور","دور")],
        default="شقة", verbose_name="نوع السكن"
    )
    housing_ownership = models.CharField(
        max_length=10, choices=[("ملك","ملك"), ("إيجار","إيجار")],
        default="إيجار", verbose_name="ملكية السكن"
    )
    receives_aid = models.BooleanField(default=False, verbose_name="هل تحصل على كرت مازيد بسهولة؟")
    monthly_aid_amount = models.CharField(max_length=50, blank=True, verbose_name="قيمة المساعدة إن وُجدت")

    # صحية
    health_asthma = models.BooleanField(default=False, verbose_name="ربو شعبي")
    health_diabetes = models.BooleanField(default=False, verbose_name="سكر الدم")
    health_epilepsy = models.BooleanField(default=False, verbose_name="تشنجات/صرع")
    health_hearing = models.BooleanField(default=False, verbose_name="ضعف السمع")
    health_heart = models.BooleanField(default=False, verbose_name="أمراض القلب")
    health_bp = models.BooleanField(default=False, verbose_name="ضغط الدم")
    health_kidney = models.BooleanField(default=False, verbose_name="التهاب الكلى")
    health_sleep = models.BooleanField(default=False, verbose_name="النوم الكثير")
    health_vision = models.BooleanField(default=False, verbose_name="ضعف البصر")
    health_other = models.CharField(max_length=200, blank=True, verbose_name="أمراض أخرى تُذكر")

    # عسكرية
    father_military = models.BooleanField(default=False, verbose_name="هل حالة عمل الأب في السلك العسكري؟")
    at_south_border = models.BooleanField(default=False, verbose_name="هل الأب مرابط بالحد الجنوبي؟")
    injured_south = models.BooleanField(default=False, verbose_name="هل أُصيب الأب في الحد الجنوبي؟")
    father_martyr = models.BooleanField(default=False, verbose_name="هل الأب شهيد في الحد الجنوبي؟")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "نموذج الموجّه الطلابي"
        verbose_name_plural = "نماذج الموجّه الطلابي"

    def __str__(self):
        return f"نموذج الموجه للإحالة {self.referral.reference}"
