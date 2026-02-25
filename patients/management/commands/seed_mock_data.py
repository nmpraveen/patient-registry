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

    mock_profiles = [
        {"first_name": "Karthik", "last_name": "Raman", "town": "Madurai", "facility_code": "MDU"},
        {"first_name": "Nivetha", "last_name": "Sundaram", "town": "Coimbatore", "facility_code": "CBE"},
        {"first_name": "Pradeep", "last_name": "Subramanian", "town": "Tirunelveli", "facility_code": "TVL"},
        {"first_name": "Anitha", "last_name": "Balasubramaniam", "town": "Salem", "facility_code": "SLM"},
        {"first_name": "Vignesh", "last_name": "Narayanan", "town": "Erode", "facility_code": "ERD"},
        {"first_name": "Harini", "last_name": "Sivakumar", "town": "Chengalpattu", "facility_code": "CGP"},
        {"first_name": "Sathish", "last_name": "Arumugam", "town": "Trichy", "facility_code": "TRY"},
        {"first_name": "Meena", "last_name": "Rajendran", "town": "Thanjavur", "facility_code": "TNJ"},
        {"first_name": "Aravind", "last_name": "Muthukumar", "town": "Vellore", "facility_code": "VLR"},
        {"first_name": "Keerthana", "last_name": "Manikandan", "town": "Kanchipuram", "facility_code": "KPM"},
        {"first_name": "Dinesh", "last_name": "Saravanan", "town": "Tiruppur", "facility_code": "TPR"},
        {"first_name": "Yamini", "last_name": "Periyasamy", "town": "Nagapattinam", "facility_code": "NGP"},
    ]

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10)
        parser.add_argument("--reset", action="store_true", help="Delete existing case/task/activity data before seeding")

    def _build_uhid(self, profile, index, today):
        # Example: TN-MDU-260001 (state-facility-year-sequence)
        return f"TN-{profile['facility_code']}-{today:%y}{index:04d}"

    def _build_phone_number(self, index):
        # Indian mobile-style numbers with valid starting digits 6/7/8/9.
        start_digit = str(9 - ((index - 1) % 4))
        return f"{start_digit}{(700000000 + index):09d}"

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
            profile = self.mock_profiles[(i - 1) % len(self.mock_profiles)]
            uhid = self._build_uhid(profile, i, today)
            if Case.objects.filter(uhid=uhid).exists():
                continue

            bucket = i % 3
            kwargs = {
                "uhid": uhid,
                "first_name": profile["first_name"],
                "last_name": profile["last_name"],
                "phone_number": self._build_phone_number(i),
                "status": CaseStatus.ACTIVE,
                "created_by": demo_user,
                "notes": f"Demo follow-up case from {profile['town']} OPD with reachable caretaker contact.",
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
