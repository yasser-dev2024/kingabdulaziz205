from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid, os

def thread_upload_path(instance, filename):
    base, ext = os.path.splitext(filename)
    safe = base[:60].replace(" ", "_")
    tid = instance.message.thread_id or "tmp"
    return f"messages/threads/{tid}/{safe}{ext.lower()}"

def generate_reference():
    return "M-" + timezone.now().strftime("%Y") + "-" + uuid.uuid4().hex[:6].upper()

class Thread(models.Model):
    STATUS_CHOICES = [
        ("OPEN", "مفتوحة"),
        ("CLOSED", "مغلقة"),
    ]
    reference   = models.CharField(max_length=20, default=generate_reference, unique=True, editable=False)
    subject     = models.CharField("الموضوع", max_length=140)
    sender      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_threads")
    recipient   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_threads")
    status      = models.CharField("الحالة", max_length=10, choices=STATUS_CHOICES, default="OPEN")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.reference} - {self.subject}"

class Message(models.Model):
    thread     = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    author     = models.ForeignKey(User, on_delete=models.CASCADE)
    content    = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"رسالة {self.thread.reference} - {self.author.username}"

class MessageAttachment(models.Model):
    message     = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="files")
    file        = models.FileField(upload_to=thread_upload_path)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"مرفق {self.message.thread.reference}"
