from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from patients.models import (
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    Gender,
    ReviewFrequency,
    SurgicalPathway,
    build_default_tasks,
    ensure_default_departments,
)


class Command(BaseCommand):
    help = "Seed mock MEDTRACK data (default 30 cases) for local demo/testing."

    mock_profiles = [
        {"first_name": "Karthik", "last_name": "Raman", "place": "Madurai", "gender": Gender.MALE, "date_of_birth": date(1989, 3, 11), "facility_code": "MDU"},
        {"first_name": "Nivetha", "last_name": "Sundaram", "place": "Coimbatore", "gender": Gender.FEMALE, "date_of_birth": date(1996, 7, 24), "facility_code": "CBE"},
        {"first_name": "Pradeep", "last_name": "Subramanian", "place": "Tirunelveli", "gender": Gender.MALE, "date_of_birth": date(1991, 11, 5), "facility_code": "TVL"},
        {"first_name": "Anitha", "last_name": "Balasubramaniam", "place": "Salem", "gender": Gender.FEMALE, "date_of_birth": date(1994, 1, 17), "facility_code": "SLM"},
        {"first_name": "Vignesh", "last_name": "Narayanan", "place": "Erode", "gender": Gender.MALE, "date_of_birth": date(1987, 10, 9), "facility_code": "ERD"},
        {"first_name": "Harini", "last_name": "Sivakumar", "place": "Chengalpattu", "gender": Gender.FEMALE, "date_of_birth": date(1998, 5, 28), "facility_code": "CGP"},
        {"first_name": "Sathish", "last_name": "Arumugam", "place": "Trichy", "gender": Gender.MALE, "date_of_birth": date(1992, 12, 14), "facility_code": "TRY"},
        {"first_name": "Meena", "last_name": "Rajendran", "place": "Thanjavur", "gender": Gender.FEMALE, "date_of_birth": date(1993, 4, 3), "facility_code": "TNJ"},
        {"first_name": "Aravind", "last_name": "Muthukumar", "place": "Vellore", "gender": Gender.MALE, "date_of_birth": date(1990, 8, 19), "facility_code": "VLR"},
        {"first_name": "Keerthana", "last_name": "Manikandan", "place": "Kanchipuram", "gender": Gender.FEMALE, "date_of_birth": date(1997, 9, 30), "facility_code": "KPM"},
        {"first_name": "Dinesh", "last_name": "Saravanan", "place": "Tiruppur", "gender": Gender.MALE, "date_of_birth": date(1988, 2, 21), "facility_code": "TPR"},
        {"first_name": "Yamini", "last_name": "Periyasamy", "place": "Nagapattinam", "gender": Gender.FEMALE, "date_of_birth": date(1995, 6, 12), "facility_code": "NGP"},
    ]

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=30)
        parser.add_argument("--reset", action="store_true", help="Delete existing case/task/activity data before seeding")

    def _build_uhid(self, profile, index, today):
        # Example: TN-MDU-260001 (state-facility-year-sequence)
        return f"TN-{profile['facility_code']}-{today:%y}{index:04d}"

    def _build_phone_number(self, index):
        # Indian mobile-style numbers with valid starting digits 6/7/8/9.
        start_digit = str(9 - ((index - 1) % 4))
        return f"{start_digit}{(700000000 + index):09d}"

    def _build_alternate_phone_number(self, index):
        start_digit = str(6 + ((index - 1) % 4))
        return f"{start_digit}{(810000000 + index):09d}"

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

            bucket = i % 6
            kwargs = {
                "uhid": uhid,
                "first_name": profile["first_name"],
                "last_name": profile["last_name"],
                "gender": profile["gender"],
                "date_of_birth": profile["date_of_birth"],
                "age": max(today.year - profile["date_of_birth"].year, 18),
                "place": profile["place"],
                "phone_number": self._build_phone_number(i),
                "alternate_phone_number": self._build_alternate_phone_number(i),
                "status": [CaseStatus.ACTIVE, CaseStatus.COMPLETED, CaseStatus.CANCELLED, CaseStatus.LOSS_TO_FOLLOW_UP][i % 4],
                "diagnosis": [
                    "Moderate anemia",
                    "Chronic cholecystitis",
                    "Type 2 diabetes follow-up",
                    "Gestational hypertension",
                    "Thyroid nodule surveillance",
                    "Post-op wound review",
                ][(i - 1) % 6],
                "ncd_flags": [
                    ["T2DM"],
                    ["SHTN", "THYROID"],
                    ["BA"],
                    ["CKD", "CAD"],
                    ["SMOKING"],
                    [],
                ][(i - 1) % 6],
                "referred_by": ["PHC", "District Hospital", "Self", "Private Clinic"][i % 4],
                "high_risk": i % 5 == 0,
                "created_by": demo_user,
                "notes": f"Demo follow-up case from {profile['place']} OPD with reachable caretaker contact.",
            }

            if bucket in (1, 4) and profile["gender"] != Gender.MALE:
                case = Case.objects.create(
                    category=anc,
                    lmp=today - timedelta(days=50 + i),
                    edd=today + timedelta(days=180 - i),
                    usg_edd=today + timedelta(days=175 - i),
                    gravida=2 + (i % 2),
                    para=1,
                    abortions=i % 2,
                    living=1,
                    **kwargs,
                )
            elif bucket in (2, 5):
                case = Case.objects.create(
                    category=surgery,
                    surgical_pathway=SurgicalPathway.PLANNED_SURGERY if bucket == 2 else SurgicalPathway.SURVEILLANCE,
                    surgery_done=bucket == 2 and i % 8 == 0,
                    surgery_date=today + timedelta(days=7 + i) if bucket == 2 else None,
                    review_date=today + timedelta(days=14 + i) if bucket == 5 else None,
                    **kwargs,
                )
            else:
                case = Case.objects.create(
                    category=non_surgical,
                    review_frequency=[
                        ReviewFrequency.MONTHLY,
                        ReviewFrequency.QUARTERLY,
                        ReviewFrequency.HALF_YEARLY,
                        ReviewFrequency.YEARLY,
                    ][(i - 1) % 4],
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
