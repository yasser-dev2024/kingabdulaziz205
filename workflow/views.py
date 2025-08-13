from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

# لو عندك موديل الإحالات باسم Referral داخل تطبيق referrals
from referrals.models import Referral


@login_required
def reports_view(request):
    # إحصائيات سريعة للتجربة؛ حسّنها لاحقًا كما تريد
    qs = Referral.objects.all()
    totals = {
        "all": qs.count(),
        "open": qs.exclude(status="CLOSED").count(),
        "closed": qs.filter(status="CLOSED").count(),
        "sent": qs.filter(created_by=request.user).count(),
        "inbox": qs.filter(assignee=request.user).count(),
        "last_30": qs.filter(created_at__gte=timezone.now() - timedelta(days=30)).count(),
    }
    return render(request, "workflow/reports.html", {"totals": totals})
