# accounts/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    # هذا النص سيظهر كعنوان للتطبيق داخل لوحة الإدارة
    verbose_name = _("الحسابات")
