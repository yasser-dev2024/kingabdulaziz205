# referrals/counselor_models.py
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .models import Referral  # نستخدم موديلك كما هو

class CounselorIntake(models.Model):
    referral = models.OneToOneField(
        Referral, on_delete=models.CASCADE,
        related_name="counselor_intake", verbose_name=_("الإحالة")
    )

    # أساسي
    counselor_name = models.CharField(_("اسم الموجّه"), max_length=150)

    # ————— المعلومات الاجتماعية/التعليمية —————
    father_alive = models.BooleanField(_("هل الأب على قيد الحياة؟"), null=True, blank=True)
    mother_alive = models.BooleanField(_("هل الأم على قيد الحياة؟"), null=True, blank=True)

    class ParentsStatus(models.TextChoices):
        STABLE = "stable", _("مستقران")
        SEPARATED = "separated", _("منفصلان")

    parents_status = models.CharField(
        _("الحالة الاجتماعية للوالدين"),
        max_length=12, choices=ParentsStatus.choices, blank=True
    )

    siblings_count = models.PositiveIntegerField(_("عدد الإخوة والأخوات"), null=True, blank=True)
    birth_order = models.CharField(_("ترتيب الطالب بين إخوته وأخواته"), max_length=50, blank=True)

    EDU_CHOICES = [
        ("illiteracy", _("يقرأ ويكتب")),
        ("primary", _("الابتدائية")),
        ("middle", _("المتوسطة")),
        ("high", _("الثانوية")),
        ("bachelor", _("بكالوريوس")),
        ("master", _("ماجستير")),
        ("phd", _("دكتوراه")),
    ]
    father_education = models.CharField(_("المستوى التعليمي للأب"), max_length=20, choices=EDU_CHOICES, blank=True)
    mother_education = models.CharField(_("المستوى التعليمي للأم"), max_length=20, choices=EDU_CHOICES, blank=True)

    # ————— المعلومات الاقتصادية —————
    father_job = models.CharField(_("مهنة الأب"), max_length=120, blank=True)
    mother_job = models.CharField(_("مهنة الأم"), max_length=120, blank=True)

    INCOME_CHOICES = [
        ("lt5", _("أقل من (٥,٠٠٠) ريال")),
        ("5to10", _("من (٥,٠٠٠) إلى (١٠,٠٠٠) ريال")),
        ("10to20", _("من (١٠,٠٠٠) إلى (٢٠,٠٠٠) ريال")),
        ("gt20", _("أكثر من (٢٠,٠٠٠) ريال")),
    ]
    family_income = models.CharField(_("دخل الأسرة"), max_length=10, choices=INCOME_CHOICES, blank=True)

    receives_social_support = models.BooleanField(_("هل يتم صرف ضمان اجتماعي لكم؟"), null=True, blank=True)

    HOUSE_OWNERSHIP = [
        ("own", _("ملك")),
        ("rent", _("إيجار")),
        ("grant", _("هبة")),
        ("waqf", _("وقف")),
        ("other", _("أخرى")),
    ]
    house_ownership = models.CharField(_("ملكية السكن"), max_length=10, choices=HOUSE_OWNERSHIP, blank=True)

    HOUSE_TYPE = [
        ("apartment", _("شقة")),
        ("villa", _("فيلا")),
        ("floor", _("دور")),
        ("traditional", _("بيت شعبي")),
        ("other", _("نوع آخر")),
    ]
    house_type = models.CharField(_("نوع السكن"), max_length=20, choices=HOUSE_TYPE, blank=True)
    house_type_other = models.CharField(_("نوع سكن (أخرى)"), max_length=120, blank=True)

    gets_everything_easily = models.BooleanField(_("هل تحصل على كل ما تريد بسهولة؟"), null=True, blank=True)

    # ————— المعلومات الصحية (checkboxes) —————
    disease_heart = models.BooleanField(_("أمراض القلب"), default=False)
    disease_pressure = models.BooleanField(_("ضغط الدم"), default=False)
    disease_kidney = models.BooleanField(_("الفشل الكلوي"), default=False)
    disease_sleep = models.BooleanField(_("النوم المرضي"), default=False)
    disease_vision = models.BooleanField(_("ضعف البصر"), default=False)
    disease_other = models.CharField(_("أمراض أخرى تُذكر"), max_length=200, blank=True)

    cond_asthma = models.BooleanField(_("ربو شعبي"), default=False)
    cond_diabetes = models.BooleanField(_("سكر الدم"), default=False)
    cond_anemia = models.BooleanField(_("فقر الدم"), default=False)
    cond_tonsils = models.BooleanField(_("التهاب اللوزتين"), default=False)
    cond_seizures = models.BooleanField(_("تشنجات/صرع"), default=False)
    cond_hearing = models.BooleanField(_("ضعف السمع"), default=False)
    cond_allergy = models.BooleanField(_("حساسية موسمية"), default=False)
    cond_rheumatism = models.BooleanField(_("روماتيزم"), default=False)
    cond_disability = models.BooleanField(_("إعاقة أحد الأعضاء"), default=False)

    # ————— المعلومات العسكرية —————
    father_in_military = models.BooleanField(_("هل حالة عمل الأب في السلك العسكري؟"), null=True, blank=True)
    father_served_southern = models.BooleanField(_("هل أُصيب الأب في الحد الجنوبي؟"), null=True, blank=True)
    father_is_martyr_south = models.BooleanField(_("هل هو شهيد/في الحد الجنوبي؟"), null=True, blank=True)

    # ————— حقول نصية عامة —————
    student_behavior = models.TextField(_("وصف السلوك/المشكلة"), blank=True)
    previous_interventions = models.TextField(_("إجراءات سابقة (إن وُجدت)"), blank=True)
    recommendations = models.TextField(_("التوصيات"), blank=True)
    follow_up_date = models.DateField(_("تاريخ المتابعة"), null=True, blank=True)

    # تتبع
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="created_counselor_intakes", verbose_name=_("أنشئ بواسطة")
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="updated_counselor_intakes", verbose_name=_("آخر تعديل بواسطة")
    )
    created_at = models.DateTimeField(_("أُنشئ في"), auto_now_add=True)
    updated_at = models.DateTimeField(_("عُدّل في"), auto_now=True)

    class Meta:
        verbose_name = _("نموذج بيانات الموجّه")
        verbose_name_plural = _("نماذج بيانات الموجّه")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.referral} — نموذج الموجّه"
