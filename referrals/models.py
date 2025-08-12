from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import os

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

# ========= إجراءات / ردود على الإحالة =========
class Action(models.Model):
    KIND_CHOICES = [
        ("REPLY", "رد"),
        ("NOTE", "ملاحظة"),
        ("DECISION", "قرار"),
    ]
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name="actions")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default="REPLY")
    content = models.TextField(blank=True)  # يسمح برد بدون نص إذا فيه ملفات
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_kind_display()} - {self.referral.reference}"

class ActionAttachment(models.Model):
    action = models.ForeignKey(Action, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to=action_upload_path)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def action_id(self):
        return self.action_id

    def __str__(self):
        return f"مرفق إجراء {self.action_id}"
