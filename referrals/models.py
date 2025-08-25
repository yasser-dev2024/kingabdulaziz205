# referrals/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid, os

from .utils import make_student_key

def referral_upload_path(instance, filename):
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    return f"referrals/{instance.referral_id}/{safe}{ext.lower()}"

def action_upload_path(instance, filename):
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    action_id = instance.action_id or "tmp"
    return f"referrals/actions/{action_id}/{safe}{ext.lower()}"

def generate_reference():
    return "R-" + timezone.now().strftime("%Y") + "-" + uuid.uuid4().hex[:6].upper()

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

    reference = models.CharField("المرجع", max_length=20, default=generate_reference, unique=True, editable=False)

    # بيانات الطالب
    student_name = models.CharField("اسم الطالب", max_length=120)
    # المفتاح الموحد للطالب (يُملأ تلقائيًا من الاسم) ويُستخدم للتجميع
    student_key = models.CharField("معرّف الطالب", max_length=180, blank=True, db_index=True)

    grade = models.CharField("الصف", max_length=2, choices=GRADE_CHOICES)
    referral_type = models.CharField("نوع الإحالة", max_length=20, choices=TYPE_CHOICES)
    details = models.TextField("التفاصيل")
    status = models.CharField("الحالة", max_length=20, choices=STATUS_CHOICES, default="NEW")

    created_by = models.ForeignKey(User, verbose_name="أنشأها", on_delete=models.CASCADE, related_name="created_referrals")
    assignee = models.ForeignKey(User, verbose_name="المكلّف", on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_referrals")

    created_at = models.DateTimeField("أُنشئت في", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "إحالة"
        verbose_name_plural = "إحالات"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # توليد مفتاح الطالب إن كان فارغًا
        if not self.student_key:
            self.student_key = make_student_key(self.student_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - {self.student_name}"

    @property
    def referral_id(self):
        return self.pk or "tmp"

class Attachment(models.Model):
    referral = models.ForeignKey(Referral, verbose_name="الإحالة", on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField("الملف", upload_to=referral_upload_path)
    uploaded_by = models.ForeignKey(User, verbose_name="تم الرفع بواسطة", on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField("تاريخ الرفع", auto_now_add=True)

    class Meta:
        verbose_name = "مرفق إحالة"
        verbose_name_plural = "مرفقات الإحالات"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"مرفق {self.referral.reference}"

class Action(models.Model):
    KIND_CHOICES = [
        ("REPLY", "رد"),
        ("NOTE", "ملاحظة"),
        ("DECISION", "قرار"),
    ]
    referral = models.ForeignKey(Referral, verbose_name="الإحالة", on_delete=models.CASCADE, related_name="actions")
    author = models.ForeignKey(User, verbose_name="الكاتب", on_delete=models.CASCADE)
    kind = models.CharField("النوع", max_length=12, choices=KIND_CHOICES, default="REPLY")
    content = models.TextField("المحتوى", blank=True)
    created_at = models.DateTimeField("أُنشئ في", auto_now_add=True)

    class Meta:
        verbose_name = "إجراء"
        verbose_name_plural = "إجراءات"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} - {self.referral.reference}"

class ActionAttachment(models.Model):
    action = models.ForeignKey(Action, verbose_name="الإجراء", on_delete=models.CASCADE, related_name="files")
    file = models.FileField("الملف", upload_to=action_upload_path)
    uploaded_by = models.ForeignKey(User, verbose_name="تم الرفع بواسطة", on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField("تاريخ الرفع", auto_now_add=True)

    class Meta:
        verbose_name = "مرفق إجراء"
        verbose_name_plural = "مرفقات الإجراءات"
        ordering = ["-uploaded_at"]

    @property
    def action_id(self):
        # إرجاع معرّف الإجراء المرتبط دون تعارض مع اسم الخاصية التلقائي
        a = getattr(self, "action", None)
        return a.pk if a and a.pk else None

    def __str__(self):
        return f"مرفق إجراء {self.action_id}"

# =========================
# شريط إخباري قابل للإدارة
# =========================
class NewsTicker(models.Model):
    text       = models.CharField("نص الشريط", max_length=300)
    is_active  = models.BooleanField("مفعل", default=True)
    starts_at  = models.DateTimeField("يبدأ من", blank=True, null=True)
    ends_at    = models.DateTimeField("ينتهي في", blank=True, null=True)
    created_at = models.DateTimeField("أُنشئ في", auto_now_add=True)

    class Meta:
        verbose_name = "شريط إخباري"
        verbose_name_plural = "أشرطة إخبارية"
        ordering = ["-created_at"]

    def __str__(self):
        return (self.text[:40] + "…") if len(self.text) > 40 else self.text

    @property
    def is_visible(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True
