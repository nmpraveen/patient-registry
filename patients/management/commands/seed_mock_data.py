from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from patients.models import (
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    ReviewFrequency,
    SurgicalPathway,
    build_default_tasks,
    ensure_default_departments,
)


class Command(BaseCommand):
    help = "Seed mock MEDTRACK data (default 10 cases) for local demo/testing."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10)
        parser.add_argument("--reset", action="store_true", help="Delete existing case/task/activity data before seeding")

    def handle(self, *args, **options):
        count = max(options["count"], 1)
        reset = options["reset"]

        ensure_default_departments()
        anc = DepartmentConfig.objects.get(name="ANC")
        surgery = DepartmentConfig.objects.get(name="Surgery")
        non_surgical = DepartmentConfig.objects.get(name="Non Surgical")

        if reset:
            CaseActivityLog.objects.all().delete()
            Case.objects.all().delete()

        User = get_user_model()
        demo_user, _ = User.objects.get_or_create(username="demo_seed")
        if not demo_user.has_usable_password():
            demo_user.set_password("demo12345")
            demo_user.save(update_fields=["password"])

        today = timezone.localdate()
        created = 0
        for i in range(1, count + 1):
            uhid = f"MOCK-{i:03d}"
            if Case.objects.filter(uhid=uhid).exists():
                continue

            bucket = i % 3
            kwargs = {
                "uhid": uhid,
                "patient_name": f"Mock Patient {i}",
                "phone_number": f"9{i:09d}"[-10:],
                "status": CaseStatus.ACTIVE,
                "created_by": demo_user,
                "notes": "Seeded demo case",
            }

            if bucket == 1:
                case = Case.objects.create(
                    category=anc,
                    lmp=today - timedelta(days=50 + i),
                    edd=today + timedelta(days=180 - i),
                    **kwargs,
                )
            elif bucket == 2:
                case = Case.objects.create(
                    category=surgery,
                    surgical_pathway=SurgicalPathway.PLANNED_SURGERY,
                    surgery_date=today + timedelta(days=7 + i),
                    **kwargs,
                )
            else:
                case = Case.objects.create(
                    category=non_surgical,
                    review_frequency=ReviewFrequency.MONTHLY,
                    review_date=today + timedelta(days=10 + i),
                    **kwargs,
                )

            tasks = build_default_tasks(case, demo_user)
            CaseActivityLog.objects.create(
                case=case,
                user=demo_user,
                note=f"Mock case seeded with {len(tasks)} starter tasks",
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeding complete. Created {created} new cases. Total cases: {Case.objects.count()}"))
