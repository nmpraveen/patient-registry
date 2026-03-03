from datetime import date, timedelta
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from patients.models import (
    AncHighRiskReason,
    CallLog,
    CallOutcome,
    Case,
    CaseActivityLog,
    CaseStatus,
    DepartmentConfig,
    Gender,
    ReviewFrequency,
    SurgicalPathway,
    TaskStatus,
    VitalEntry,
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
        parser.add_argument("--count", type=int)
        parser.add_argument(
            "--profile",
            choices=["smoke", "full"],
            default="full",
            help="Seeding profile preset. smoke creates fewer deterministic cases than full.",
        )
        parser.add_argument(
            "--include-vitals",
            action="store_true",
            help="Seed vital-entry history for selected cases.",
        )
        parser.add_argument(
            "--include-rch-scenarios",
            action="store_true",
            help="Include ANC scenarios where RCH number is missing/bypassed.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete previously seeded mock cases and linked call/activity logs before seeding",
        )
        parser.add_argument(
            "--reset-all",
            action="store_true",
            help="Delete all case data (cases/call logs/activity logs) before seeding",
        )

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

    def _base_case_kwargs(self, profile, index, today, demo_user):
        return {
            "uhid": self._build_uhid(profile, index, today),
            "first_name": profile["first_name"],
            "last_name": profile["last_name"],
            "gender": profile["gender"],
            "date_of_birth": profile["date_of_birth"],
            "age": max(today.year - profile["date_of_birth"].year, 18),
            "place": profile["place"],
            "phone_number": self._build_phone_number(index),
            "alternate_phone_number": self._build_alternate_phone_number(index),
            "status": [CaseStatus.ACTIVE, CaseStatus.COMPLETED, CaseStatus.CANCELLED, CaseStatus.LOSS_TO_FOLLOW_UP][index % 4],
            "diagnosis": [
                "Moderate anemia",
                "Chronic cholecystitis",
                "Type 2 diabetes follow-up",
                "Gestational hypertension",
                "Thyroid nodule surveillance",
                "Post-op wound review",
            ][(index - 1) % 6],
            "ncd_flags": [["T2DM"], ["SHTN", "THYROID"], ["BA"], ["CKD", "CAD"], ["SMOKING"], []][(index - 1) % 6],
            "referred_by": ["PHC", "District Hospital", "Self", "Private Clinic"][index % 4],
            "high_risk": index % 5 == 0,
            "created_by": demo_user,
            "metadata": {
                "seed_profile": profile["facility_code"],
                "source": "seed_mock_data",
                "seed_rng": 20260226,
            },
            "notes": f"Demo follow-up case from {profile['place']} OPD with reachable caretaker contact.",
        }

    def build_anc_high_risk_case(self, anc, today, kwargs):
        scenario = "anc_high_risk"
        kwargs["metadata"]["seed_scenario"] = scenario
        kwargs.update(
            {
                "category": anc,
                "status": CaseStatus.ACTIVE,
                "high_risk": True,
                "lmp": today - timedelta(days=218),
                "edd": today + timedelta(days=64),
                "usg_edd": today + timedelta(days=61),
                "gravida": 3,
                "para": 1,
                "abortions": 1,
                "living": 1,
                "anc_high_risk_reasons": [AncHighRiskReason.ANEMIA, AncHighRiskReason.PIH],
                "rch_number": f"{730000000000 + int(kwargs['uhid'][-4:]):012d}",
                "rch_bypass": False,
                "diagnosis": "ANC high risk - anemia with PIH",
            }
        )
        return Case.objects.create(**kwargs), scenario

    def build_anc_rch_missing_case(self, anc, today, kwargs):
        scenario = "anc_rch_missing"
        kwargs["metadata"]["seed_scenario"] = scenario
        kwargs.update(
            {
                "category": anc,
                "status": CaseStatus.ACTIVE,
                "high_risk": False,
                "lmp": today - timedelta(days=130),
                "edd": today + timedelta(days=150),
                "usg_edd": today + timedelta(days=146),
                "gravida": 2,
                "para": 1,
                "abortions": 0,
                "living": 1,
                "rch_number": "",
                "rch_bypass": True,
                "diagnosis": "ANC follow-up awaiting RCH registration",
            }
        )
        return Case.objects.create(**kwargs), scenario

    def build_surgery_planned_case(self, surgery, today, kwargs):
        scenario = "surgery_planned"
        kwargs["metadata"]["seed_scenario"] = scenario
        kwargs.update(
            {
                "category": surgery,
                "status": CaseStatus.ACTIVE,
                "surgical_pathway": SurgicalPathway.PLANNED_SURGERY,
                "surgery_done": False,
                "surgery_date": today + timedelta(days=6),
                "diagnosis": "Cholelithiasis planned surgery",
            }
        )
        return Case.objects.create(**kwargs), scenario

    def build_non_surgical_overdue_case(self, non_surgical, today, kwargs):
        scenario = "non_surgical_overdue"
        kwargs["metadata"]["seed_scenario"] = scenario
        kwargs.update(
            {
                "category": non_surgical,
                "status": CaseStatus.ACTIVE,
                "review_frequency": ReviewFrequency.MONTHLY,
                "review_date": today - timedelta(days=7),
                "diagnosis": "Diabetes follow-up overdue review",
            }
        )
        return Case.objects.create(**kwargs), scenario

    def build_default_case(self, anc, surgery, non_surgical, today, kwargs, index):
        bucket = index % 6
        scenario = "default_mixed"
        kwargs["metadata"]["seed_scenario"] = scenario
        if bucket in (1, 4) and kwargs["gender"] != Gender.MALE:
            kwargs.update(
                {
                    "category": anc,
                    "lmp": today - timedelta(days=50 + index),
                    "edd": today + timedelta(days=180 - index),
                    "usg_edd": today + timedelta(days=175 - index),
                    "gravida": 2 + (index % 2),
                    "para": 1,
                    "abortions": index % 2,
                    "living": 1,
                    "rch_number": f"{720000000000 + index:012d}",
                }
            )
            return Case.objects.create(**kwargs), scenario
        if bucket in (2, 5):
            kwargs.update(
                {
                    "category": surgery,
                    "surgical_pathway": SurgicalPathway.PLANNED_SURGERY if bucket == 2 else SurgicalPathway.SURVEILLANCE,
                    "surgery_done": bucket == 2 and index % 8 == 0,
                    "surgery_date": today + timedelta(days=7 + index) if bucket == 2 else None,
                    "review_date": today + timedelta(days=14 + index) if bucket == 5 else None,
                }
            )
            return Case.objects.create(**kwargs), scenario
        kwargs.update(
            {
                "category": non_surgical,
                "review_frequency": [ReviewFrequency.MONTHLY, ReviewFrequency.QUARTERLY, ReviewFrequency.HALF_YEARLY, ReviewFrequency.YEARLY][
                    (index - 1) % 4
                ],
                "review_date": today + timedelta(days=10 + index),
            }
        )
        return Case.objects.create(**kwargs), scenario

    def mutate_seeded_tasks(self, case, rng, today):
        tasks = list(case.tasks.order_by("due_date", "id")[:4])
        if not tasks:
            return
        tasks[0].due_date = today - timedelta(days=5)
        tasks[0].status = TaskStatus.SCHEDULED
        tasks[0].save(update_fields=["due_date", "status", "completed_at", "updated_at"])
        if len(tasks) > 1:
            tasks[1].due_date = today
            tasks[1].status = TaskStatus.AWAITING_REPORTS
            tasks[1].save(update_fields=["due_date", "status", "completed_at", "updated_at"])
        if len(tasks) > 2:
            tasks[2].due_date = today + timedelta(days=7)
            tasks[2].status = TaskStatus.SCHEDULED
            tasks[2].save(update_fields=["due_date", "status", "completed_at", "updated_at"])
        if len(tasks) > 3:
            tasks[3].due_date = today - timedelta(days=1)
            tasks[3].status = TaskStatus.COMPLETED
            tasks[3].save(update_fields=["due_date", "status", "completed_at", "updated_at"])
        for extra in case.tasks.exclude(id__in=[task.id for task in tasks]):
            if rng.random() < 0.2:
                extra.status = TaskStatus.CANCELLED
                extra.save(update_fields=["status", "completed_at", "updated_at"])

    def seed_vitals_for_case(self, case, demo_user, today):
        if case.category.name.upper() == "ANC":
            samples = [
                (today - timedelta(days=14), 138, 92, 90, 99, 58.4, 9.2),
                (today - timedelta(days=4), 132, 88, 86, 99, 58.9, 9.5),
            ]
        else:
            samples = [
                (today - timedelta(days=10), 128, 84, 82, 98, 67.1, None),
                (today - timedelta(days=2), 124, 82, 80, 98, 67.0, None),
            ]
        for day, sys, dia, pr, spo2, wt, hb in samples:
            VitalEntry.objects.create(
                case=case,
                recorded_at=timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time())) + timedelta(hours=9),
                bp_systolic=sys,
                bp_diastolic=dia,
                pr=pr,
                spo2=spo2,
                weight_kg=wt,
                hemoglobin=hb,
                created_by=demo_user,
                updated_by=demo_user,
            )

    def seed_calls_for_case(self, case, demo_user, scenario, rng):
        task_choices = list(case.tasks.order_by("due_date", "id")[:3])
        scenario_outcomes = {
            "anc_high_risk": [CallOutcome.CALL_BACK_LATER, CallOutcome.ANSWERED_CONFIRMED_VISIT],
            "anc_rch_missing": [CallOutcome.NO_ANSWER, CallOutcome.INVALID_NUMBER],
            "surgery_planned": [CallOutcome.ANSWERED_UNCERTAIN, CallOutcome.ANSWERED_CONFIRMED_VISIT],
            "non_surgical_overdue": [CallOutcome.CALL_REJECTED, CallOutcome.PATIENT_DECLINED],
        }
        outcomes = scenario_outcomes.get(
            scenario,
            [
                rng.choice([CallOutcome.NO_ANSWER, CallOutcome.SWITCHED_OFF, CallOutcome.CALL_BACK_LATER]),
                rng.choice([CallOutcome.ANSWERED_UNCERTAIN, CallOutcome.PATIENT_SHIFTED, CallOutcome.RUDE_BEHAVIOR]),
            ],
        )
        for attempt, outcome in enumerate(outcomes, start=1):
            task = task_choices[(attempt - 1) % len(task_choices)] if task_choices and attempt % 2 == 1 else None
            call_log = CallLog.objects.create(
                case=case,
                task=task,
                outcome=outcome,
                notes=f"Seeded {scenario} call attempt #{attempt}",
                staff_user=demo_user,
            )
            CaseActivityLog.objects.create(
                case=case,
                task=call_log.task,
                user=demo_user,
                note=f"Call outcome logged: {call_log.get_outcome_display()}",
            )

    def handle(self, *args, **options):
        profile = options["profile"]
        count = options["count"] if options["count"] is not None else (12 if profile == "smoke" else 30)
        count = max(count, 1)
        reset = options["reset"]
        reset_all = options["reset_all"]
        include_vitals = options["include_vitals"]
        include_rch_scenarios = options["include_rch_scenarios"]

        if reset and reset_all:
            raise CommandError("Use either --reset or --reset-all, not both.")

        ensure_default_departments()
        anc = DepartmentConfig.objects.get(name="ANC")
        surgery = DepartmentConfig.objects.get(name="Surgery")
        non_surgical = DepartmentConfig.objects.get(name="Non Surgical")

        if reset_all:
            CallLog.objects.all().delete()
            CaseActivityLog.objects.all().delete()
            Case.objects.all().delete()
        elif reset:
            seeded_cases = Case.objects.filter(metadata__source="seed_mock_data")
            CallLog.objects.filter(case__in=seeded_cases).delete()
            CaseActivityLog.objects.filter(case__in=seeded_cases).delete()
            seeded_cases.delete()

        User = get_user_model()
        demo_user, _ = User.objects.get_or_create(username="demo_seed")
        if demo_user.has_usable_password():
            demo_user.set_unusable_password()
            demo_user.save(update_fields=["password"])

        today = timezone.localdate()
        rng = random.Random(20260226)
        created = 0
        named_builders = [
            lambda anc, surgery, non_surgical, today, kwargs, _: self.build_anc_high_risk_case(anc, today, kwargs),
            lambda anc, surgery, non_surgical, today, kwargs, _: self.build_surgery_planned_case(surgery, today, kwargs),
            lambda anc, surgery, non_surgical, today, kwargs, _: self.build_non_surgical_overdue_case(non_surgical, today, kwargs),
        ]
        if include_rch_scenarios:
            named_builders.insert(1, lambda anc, surgery, non_surgical, today, kwargs, _: self.build_anc_rch_missing_case(anc, today, kwargs))

        for i in range(1, count + 1):
            profile = self.mock_profiles[(i - 1) % len(self.mock_profiles)]
            uhid = self._build_uhid(profile, i, today)
            if Case.objects.filter(uhid=uhid).exists():
                continue
            kwargs = self._base_case_kwargs(profile, i, today, demo_user)

            if i <= len(named_builders):
                case, scenario = named_builders[i - 1](anc, surgery, non_surgical, today, kwargs, i)
            else:
                case, scenario = self.build_default_case(anc, surgery, non_surgical, today, kwargs, i)

            tasks = build_default_tasks(case, demo_user)
            self.mutate_seeded_tasks(case, rng, today)
            CaseActivityLog.objects.create(
                case=case,
                user=demo_user,
                note=f"Mock case seeded with scenario '{scenario}' and {len(tasks)} starter tasks",
            )

            self.seed_calls_for_case(case, demo_user, scenario, rng)
            if include_vitals and scenario in {"anc_high_risk", "non_surgical_overdue", "default_mixed"}:
                self.seed_vitals_for_case(case, demo_user, today)
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeding complete. Created {created} new cases. Total cases: {Case.objects.count()}"))
