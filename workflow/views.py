# C:\Users\Test2\kingabdulaziz205\workflow\views.py
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q

# لو عندك موديل الإحالات باسم Referral داخل تطبيق referrals
from referrals.models import Referral


@login_required
def reports_view(request):
    # إظهار التقارير لكل مستخدم بناءً على ما أرسله أو ما وُكّل إليه فقط
    base_qs = (
        Referral.objects.filter(Q(created_by=request.user) | Q(assignee=request.user))
        .distinct()
    )

    now = timezone.now()
    last_30_dt = now - timedelta(days=30)

    totals = {
        "all": base_qs.count(),                                  # إجمالي إحالاتي (مرسلة + واردة لي)
        "open": base_qs.exclude(status="CLOSED").count(),        # المفتوحة/قيد المراجعة من إحالاتي
        "closed": base_qs.filter(status="CLOSED").count(),       # المغلقة من إحالاتي
        "sent": base_qs.filter(created_by=request.user).count(), # أرسلتها أنا
        "inbox": base_qs.filter(assignee=request.user).count(),  # واردة إليّ
        "last_30": base_qs.filter(created_at__gte=last_30_dt).count(),  # خلال 30 يومًا من إحالاتي
    }
    return render(request, "workflow/reports.html", {"totals": totals})
