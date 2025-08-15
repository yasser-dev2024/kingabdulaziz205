# referrals/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _

CounselorIntake = None
try:
    from .models import CounselorIntake as _CI
    CounselorIntake = _CI
except Exception:
    try:
        from .counselor_models import CounselorIntake as _CI
        CounselorIntake = _CI
    except Exception:
        pass


class YesNoNullSelect(forms.Select):
    def __init__(self, *args, **kwargs):
        choices = (( "", "—"), ("True", "نعم"), ("False", "لا"))
        super().__init__(choices=choices, *args, **kwargs)


class CounselorIntakeForm(forms.ModelForm):
    class Meta:
        model = CounselorIntake
        fields = [
            "counselor_name",

            "father_alive", "mother_alive", "parents_status",
            "siblings_count", "birth_order",
            "father_education", "mother_education",

            "father_job", "mother_job", "family_income",
            "receives_social_support", "house_ownership",
            "house_type", "house_type_other", "gets_everything_easily",

            "disease_heart", "disease_pressure", "disease_kidney",
            "disease_sleep", "disease_vision", "disease_other",
            "cond_asthma", "cond_diabetes", "cond_anemia",
            "cond_tonsils", "cond_seizures", "cond_hearing",
            "cond_allergy", "cond_rheumatism", "cond_disability",

            "father_in_military", "father_served_southern", "father_is_martyr_south",

            "student_behavior", "previous_interventions",
            "recommendations", "follow_up_date",
        ]
        widgets = {
            "student_behavior": forms.Textarea(attrs={"rows": 3}),
            "previous_interventions": forms.Textarea(attrs={"rows": 3}),
            "recommendations": forms.Textarea(attrs={"rows": 3}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),

            "father_alive": YesNoNullSelect(),
            "mother_alive": YesNoNullSelect(),
            "receives_social_support": YesNoNullSelect(),
            "gets_everything_easily": YesNoNullSelect(),
            "father_in_military": YesNoNullSelect(),
            "father_served_southern": YesNoNullSelect(),
            "father_is_martyr_south": YesNoNullSelect(),
        }
        labels = {
            "counselor_name": _("اسم الموجّه"),

            "father_alive": _("هل الأب على قيد الحياة؟"),
            "mother_alive": _("هل الأم على قيد الحياة؟"),
            "parents_status": _("الحالة الاجتماعية للوالدين"),
            "siblings_count": _("عدد الإخوة والأخوات"),
            "birth_order": _("ترتيب الطالب بين إخوته وأخواته"),
            "father_education": _("المستوى التعليمي للأب"),
            "mother_education": _("المستوى التعليمي للأم"),

            "father_job": _("مهنة الأب"),
            "mother_job": _("مهنة الأم"),
            "family_income": _("دخل الأسرة"),
            "receives_social_support": _("هل يتم صرف ضمان اجتماعي لكم؟"),
            "house_ownership": _("ملكية السكن"),
            "house_type": _("نوع السكن"),
            "house_type_other": _("نوع سكن (أخرى)"),
            "gets_everything_easily": _("هل تحصل على كل ما تريد بسهولة؟"),

            "disease_heart": _("أمراض القلب"),
            "disease_pressure": _("ضغط الدم"),
            "disease_kidney": _("الفشل الكلوي"),
            "disease_sleep": _("النوم المرضي"),
            "disease_vision": _("ضعف البصر"),
            "disease_other": _("أمراض أخرى تُذكر"),

            "cond_asthma": _("ربو شعبي"),
            "cond_diabetes": _("سكر الدم"),
            "cond_anemia": _("فقر الدم"),
            "cond_tonsils": _("التهاب اللوزتين"),
            "cond_seizures": _("تشنجات/صرع"),
            "cond_hearing": _("ضعف السمع"),
            "cond_allergy": _("حساسية موسمية"),
            "cond_rheumatism": _("روماتيزم"),
            "cond_disability": _("إعاقة أحد الأعضاء"),

            "father_in_military": _("هل حالة عمل الأب في السلك العسكري؟"),
            "father_served_southern": _("هل أُصيب الأب في الحد الجنوبي؟"),
            "father_is_martyr_south": _("هل هو شهيد/في الحد الجنوبي؟"),

            "previous_interventions": _("إجراءات سابقة (اختياري)"),
            "recommendations": _("التوصيات (اختياري)"),
            "follow_up_date": _("تاريخ المتابعة"),
        }
