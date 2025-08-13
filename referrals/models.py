# C:\Users\Test2\kingabdulaziz205\referrals\models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid
import os


def referral_upload_path(instance, filename):
    # instance = Attachment
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    rid = str(instance.referral_id or "tmp")  # FK raw id المتوفر تلقائيًا من Django
    return f"referrals/{rid}/{safe}{ext.lower()}"


def action_upload_path(instance, filename):
    # instance = ActionAttachment
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    aid = str(instance.action_id or "tmp")  # FK raw id المتوفر تلقائيًا من Django
    return f"referrals/actions/{aid}/{safe}{ext.lower()}"


def generate_reference():
    return "R-" + timezone.now().strftime("%Y") + "-" + uuid.uuid4().hex[:6].upper()


class Referral(models.Model):
    STATUS_CHOICES = [
        ("NEW", _("جديدة")),
        ("UNDER_REVIEW", _("قيد المراجعة")),
        ("SENT_TO_DEPUTY", _("محالة لوكيل")),
        ("CLOSED", _("مغلقة")),
    ]

    TYPE_CHOICES = [
        ("behavior", _("سلوكي")),
        ("academic", _("تحصيلي")),
        ("health", _("صحي")),
        ("other", _("أخرى")),
    ]

    GRADE_CHOICES = [(str(i), _("الصف ") + str(i)) for i in range(1, 13)]

    reference = models.CharField(_("المرجع"), max_length=20, default=generate_reference, unique=True, editable=False)
    student_name = models.CharField(_("اسم الطالب"), max_length=120)
    grade = models.CharField(_("الصف"), max_length=2, choices=GRADE_CHOICES)
    referral_type = models.CharField(_("نوع الإحالة"), max_length=20, choices=TYPE_CHOICES)
    details = models.TextField(_("التفاصيل"))
    status = models.CharField(_("الحالة"), max_length=20, choices=STATUS_CHOICES, default="NEW")

    created_by = models.ForeignKey(
        User, verbose_name=_("أنشأها"), on_delete=models.CASCADE, related_name="created_referrals"
    )
    assignee = models.ForeignKey(
        User, verbose_name=_("المحال إليه"), on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_referrals"
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التعديل"), auto_now=True)

    class Meta:
        verbose_name = _("إحالة")
        verbose_name_plural = _("الإحالات")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.reference} - {self.student_name}"


class Attachment(models.Model):
    referral = models.ForeignKey(Referral, verbose_name=_("الإحالة"), on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(_("الملف"), upload_to=referral_upload_path)
    uploaded_by = models.ForeignKey(User, verbose_name=_("رفع بواسطة"), on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(_("تاريخ الرفع"), auto_now_add=True)

    class Meta:
        verbose_name = _("مرفق")
        verbose_name_plural = _("المرفقات")
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"{_('مرفق')} {self.referral.reference}"


class Action(models.Model):
    KIND_CHOICES = [
        ("REPLY", _("رد")),
        ("NOTE", _("ملاحظة")),
        ("DECISION", _("قرار")),
    ]

    referral = models.ForeignKey(Referral, verbose_name=_("الإحالة"), on_delete=models.CASCADE, related_name="actions")
    author = models.ForeignKey(User, verbose_name=_("الكاتب"), on_delete=models.CASCADE)
    kind = models.CharField(_("النوع"), max_length=12, choices=KIND_CHOICES, default="REPLY")
    content = models.TextField(_("النص"), blank=True)  # يسمح برد بدون نص إذا وُجدت ملفات
    created_at = models.DateTimeField(_("تاريخ الإضافة"), auto_now_add=True)

    class Meta:
        verbose_name = _("إجراء")
        verbose_name_plural = _("إجراءات")
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.get_kind_display()} - {self.referral.reference}"


class ActionAttachment(models.Model):
    action = models.ForeignKey(Action, verbose_name=_("الإجراء"), on_delete=models.CASCADE, related_name="files")
    file = models.FileField(_("الملف"), upload_to=action_upload_path)
    uploaded_by = models.ForeignKey(User, verbose_name=_("رفع بواسطة"), on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(_("تاريخ الرفع"), auto_now_add=True)

    class Meta:
        verbose_name = _("مرفق إجراء")
        verbose_name_plural = _("مرفقات الإجراءات")
        ordering = ("-uploaded_at",)

    def __str__(self):
        return f"{_('مرفق إجراء')} {self.action_id}"
