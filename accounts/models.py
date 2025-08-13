# C:\Users\Test2\kingabdulaziz205\accounts\models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

ROLE_CHOICES = [
    ("وكيل الشؤون المدرسية", "وكيل الشؤون المدرسية"),
    ("وكيل الشؤون التعليمية", "وكيل الشؤون التعليمية"),
    ("وكيل شؤون الطلاب", "وكيل شؤون الطلاب"),
    ("موجه طلابي", "موجه طلابي"),
    ("إداري", "إداري"),
    ("مدير المدرسة", "مدير المدرسة"),
    ("معلم", "معلم"),
]

class Profile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", verbose_name=_("المستخدم")
    )
    full_name = models.CharField(_("الاسم الثلاثي"), max_length=150, blank=True, default="")
    role = models.CharField(_("الدور"), max_length=50, choices=ROLE_CHOICES)

    class Meta:
        verbose_name = _("الملف الشخصي")
        verbose_name_plural = _("الملفات الشخصية")

    def __str__(self):
        return self.full_name or self.user.username

    @property
    def display_name(self):
        # مفيد للعرض في القوالب والقوائم
        return self.full_name or self.user.username
