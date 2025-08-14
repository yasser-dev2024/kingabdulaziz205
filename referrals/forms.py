from django import forms
from .models import CounselorIntake

class CounselorIntakeForm(forms.ModelForm):
    class Meta:
        model = CounselorIntake
        exclude = ("referral",)
        widgets = {
            "health_other": forms.TextInput(attrs={"placeholder": "اكتب إن وُجد"}),
            "monthly_aid_amount": forms.TextInput(attrs={"placeholder": "مثال: 500 ريال"}),
        }
