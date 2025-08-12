# C:\Users\Test2\kingabdulaziz205\accounts\models.py
from django.db import models
from django.contrib.auth.models import User

ROLE_CHOICES = [
    ("وكيل الشؤون المدرسية", "وكيل الشؤون المدرسية"),
    ("وكيل الشؤون التعليمية", "وكيل الشؤون التعليمية"),
    ("وكيل شؤون الطلاب", "وكيل شؤون الطلاب"),
    ("موجه طلابي", "موجه طلابي"),
    ("إداري", "إداري"),
    ("مدير المدرسة", "مدير المدرسة"),
    ("معلم", "معلم"),  # جديد
]

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField("الاسم الثلاثي", max_length=150)
    role = models.CharField("الدور", max_length=50, choices=ROLE_CHOICES)

    def __str__(self):
        return self.full_name or self.user.username
