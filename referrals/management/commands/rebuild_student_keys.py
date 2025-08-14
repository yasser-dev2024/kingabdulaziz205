# referrals/management/commands/rebuild_student_keys.py
from django.core.management.base import BaseCommand
from referrals.models import Referral
from referrals.utils import make_student_key

class Command(BaseCommand):
    help = "إعادة توليد student_key لكل الإحالات الحالية"

    def handle(self, *args, **options):
        updated = 0
        for r in Referral.objects.all():
            key = make_student_key(r.student_name)
            if r.student_key != key:
                r.student_key = key
                r.save(update_fields=["student_key"])
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"تم تحديث {updated} إحالة."))
