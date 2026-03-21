from datetime import date, datetime, time, timedelta
from decimal import Decimal
import random
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from patients.models import (
    ActivityEventType,
    AncHighRiskReason,
    CallLog,
    CallOutcome,
    Case,
    CaseActivityLog,
    CaseSubcategory,
    CaseStatus,
    DepartmentConfig,
    Gender,
    QUICK_ENTRY_DETAILS_TASK_TITLE,
    ReviewFrequency,
    SurgicalPathway,
    TaskType,
    TaskStatus,
    VitalEntry,
    build_default_tasks,
    create_quick_entry_details_task,
    ensure_default_departments,
    generate_quick_entry_uhid,
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
            help="Seed vital-entry history for all seeded cases.",
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
        parser.add_argument(
            "--yes-reset-all",
            action="store_true",
            help="Skip interactive confirmation prompt for --reset-all.",
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

    @staticmethod
    def _surgery_subcategory_for_index(index):
        values = [
            CaseSubcategory.GENERAL_SURGERY,
            CaseSubcategory.ORTHOPEDICS,
            CaseSubcategory.PLASTIC_SURGERY,
            CaseSubcategory.PEDIATRIC_SURGERY,
            CaseSubcategory.UROLOGY,
            CaseSubcategory.ENT,
            CaseSubcategory.OTHER_SPECIALTY,
        ]
        return values[(index - 1) % len(values)]

    @staticmethod
    def _medicine_subcategory_for_index(index):
        values = [
            CaseSubcategory.GENERAL_MEDICINE,
            CaseSubcategory.PSYCHIATRY,
            CaseSubcategory.CARDIOLOGY_ECHO,
            CaseSubcategory.PEDIATRIC,
            CaseSubcategory.MEDICAL_ONCOLOGY,
        ]
        return values[(index - 1) % len(values)]

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
                "subcategory": CaseSubcategory.GENERAL_SURGERY,
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
                "subcategory": CaseSubcategory.GENERAL_MEDICINE,
                "status": CaseStatus.ACTIVE,
                "review_frequency": ReviewFrequency.MONTHLY,
                "review_date": today - timedelta(days=7),
                "diagnosis": "Diabetes follow-up overdue review",
            }
        )
        return Case.objects.create(**kwargs), scenario

    def build_quick_entry_case(self, surgery, today, kwargs):
        scenario = "quick_entry_pending_details"
        kwargs["metadata"]["seed_scenario"] = scenario
        kwargs["metadata"]["entry_mode"] = "quick_entry"
        kwargs["metadata"]["details_pending"] = True
        kwargs.update(
            {
                "uhid": generate_quick_entry_uhid(today),
                "category": surgery,
                "status": CaseStatus.ACTIVE,
                "last_name": "",
                "place": "",
                "phone_number": "",
                "alternate_phone_number": "",
                "referred_by": "",
                "review_date": today + timedelta(days=5),
                "diagnosis": "Quick entry pending full surgical details",
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
                    "subcategory": self._surgery_subcategory_for_index(index),
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
                "subcategory": self._medicine_subcategory_for_index(index),
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
        update_fields = ["due_date", "status", "completed_at", "updated_at"]
        if tasks[0].task_type == TaskType.CUSTOM:
            tasks[0].task_type = TaskType.VISIT
            update_fields.append("task_type")
        tasks[0].save(update_fields=update_fields)
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

    def _require_reset_all_confirmation(self, yes_reset_all):
        if yes_reset_all:
            return
        if not sys.stdin or not sys.stdin.isatty():
            raise CommandError("Refusing --reset-all in non-interactive mode without --yes-reset-all.")

        confirmation = input("WARNING: --reset-all deletes ALL case/call/activity data. Type 'yes' to continue: ").strip().lower()
        if confirmation not in {"y", "yes"}:
            raise CommandError("Reset-all aborted by user.")

    def _vitals_target_count(self, profile_name):
        return 4 if profile_name == "smoke" else 6

    def _build_vitals_schedule(self, case, today, target_count):
        relevant_types = {TaskType.LAB, TaskType.VISIT, TaskType.PROCEDURE}
        task_rows = list(
            case.tasks.filter(task_type__in=relevant_types, due_date__lte=today)
            .order_by("due_date", "id")
            .values_list("due_date", "task_type")
        )
        day_to_types = {}
        for due_date, task_type in task_rows:
            day_to_types.setdefault(due_date, set()).add(task_type)

        anchor_days = sorted(day_to_types.keys())
        if len(anchor_days) >= target_count:
            selected_days = list(anchor_days[-target_count:])
        else:
            selected_days = list(anchor_days)
            cursor = (selected_days[0] if selected_days else today) - timedelta(days=21)
            while len(selected_days) < target_count:
                if cursor not in day_to_types:
                    selected_days.insert(0, cursor)
                cursor -= timedelta(days=21)
            selected_days.sort()

        return [(day, day_to_types.get(day, set())) for day in selected_days]

    def _interpolate(self, start, end, point_index, total_points):
        if total_points <= 1:
            return float(end)
        return float(start) + ((float(end) - float(start)) * point_index / (total_points - 1))

    def _clamp(self, value, minimum, maximum):
        return max(minimum, min(maximum, value))

    def _scenario_vitals_profile(self, case, scenario):
        category_name = case.category.name.upper()
        if category_name == "ANC":
            if scenario == "anc_high_risk":
                return {
                    "bp_systolic": (146, 134),
                    "bp_diastolic": (96, 86),
                    "pr": (96, 84),
                    "spo2": (97, 99),
                    "weight_kg": (56.0, 59.0),
                    "hemoglobin": (8.7, 9.8),
                    "hb_lab_only": False,
                }
            if scenario == "anc_rch_missing":
                return {
                    "bp_systolic": (132, 124),
                    "bp_diastolic": (88, 80),
                    "pr": (90, 82),
                    "spo2": (98, 99),
                    "weight_kg": (55.0, 57.5),
                    "hemoglobin": (10.2, 11.1),
                    "hb_lab_only": False,
                }
            return {
                "bp_systolic": (130, 122),
                "bp_diastolic": (86, 78),
                "pr": (88, 80),
                "spo2": (98, 99),
                "weight_kg": (56.2, 58.4),
                "hemoglobin": (10.1, 11.2),
                "hb_lab_only": False,
            }
        if category_name == "SURGERY":
            if scenario == "surgery_planned":
                return {
                    "bp_systolic": (136, 126),
                    "bp_diastolic": (88, 82),
                    "pr": (86, 78),
                    "spo2": (98, 99),
                    "weight_kg": (66.8, 66.2),
                    "hemoglobin": (11.9, 12.3),
                    "hb_lab_only": True,
                }
            return {
                "bp_systolic": (132, 124),
                "bp_diastolic": (86, 80),
                "pr": (84, 78),
                "spo2": (98, 99),
                "weight_kg": (67.2, 66.8),
                "hemoglobin": (11.6, 12.0),
                "hb_lab_only": True,
            }
        if scenario == "non_surgical_overdue":
            return {
                "bp_systolic": (152, 136),
                "bp_diastolic": (96, 88),
                "pr": (92, 84),
                "spo2": (97, 98),
                "weight_kg": (69.4, 67.3),
                "hemoglobin": (11.4, 11.0),
                "hb_lab_only": True,
            }
        return {
            "bp_systolic": (140, 128),
            "bp_diastolic": (90, 82),
            "pr": (88, 80),
            "spo2": (97, 98),
            "weight_kg": (68.2, 67.0),
            "hemoglobin": (11.5, 11.1),
            "hb_lab_only": True,
        }

    def _build_vital_values(self, profile, point_index, total_points, task_types, rng):
        systolic = int(round(self._interpolate(*profile["bp_systolic"], point_index, total_points) + rng.randint(-2, 2)))
        diastolic = int(round(self._interpolate(*profile["bp_diastolic"], point_index, total_points) + rng.randint(-2, 2)))
        pulse = int(round(self._interpolate(*profile["pr"], point_index, total_points) + rng.randint(-2, 2)))
        spo2 = int(round(self._interpolate(*profile["spo2"], point_index, total_points) + rng.randint(-1, 1)))
        weight = self._interpolate(*profile["weight_kg"], point_index, total_points) + rng.uniform(-0.25, 0.25)

        systolic = self._clamp(systolic, 100, 180)
        diastolic = self._clamp(diastolic, 60, 110)
        if diastolic >= systolic:
            diastolic = max(60, systolic - 12)
        pulse = self._clamp(pulse, 60, 120)
        spo2 = self._clamp(spo2, 93, 100)
        weight = self._clamp(weight, 35, 130)

        hb_value = None
        hb_start, hb_end = profile["hemoglobin"]
        should_seed_hb = not profile["hb_lab_only"] or TaskType.LAB in task_types or point_index == total_points - 1
        if should_seed_hb and hb_start is not None and hb_end is not None:
            hb_raw = self._interpolate(hb_start, hb_end, point_index, total_points) + rng.uniform(-0.2, 0.2)
            hb_value = Decimal(f"{self._clamp(hb_raw, 4, 13):.1f}")

        return {
            "bp_systolic": systolic,
            "bp_diastolic": diastolic,
            "pr": pulse,
            "spo2": spo2,
            "weight_kg": Decimal(f"{weight:.1f}"),
            "hemoglobin": hb_value,
        }

    def _build_recorded_at(self, day, point_index, rng):
        slots = [(8, 15), (9, 5), (10, 20), (11, 10), (12, 25), (13, 5), (14, 15)]
        slot_index = (point_index + rng.randint(0, 2)) % len(slots)
        hour, minute = slots[slot_index]
        recorded_at = timezone.make_aware(datetime.combine(day, time(hour=hour, minute=minute)))
        now = timezone.now()
        if recorded_at > now:
            recorded_at = now - timedelta(minutes=5)
        return recorded_at

    def seed_vitals_for_case(self, case, demo_user, today, rng, profile_name):
        scenario = (case.metadata or {}).get("seed_scenario", "default_mixed")
        target_count = self._vitals_target_count(profile_name)
        schedule = self._build_vitals_schedule(case, today, target_count)
        vitals_profile = self._scenario_vitals_profile(case, scenario)

        for point_index, (day, task_types) in enumerate(schedule):
            values = self._build_vital_values(vitals_profile, point_index, target_count, task_types, rng)
            VitalEntry.objects.create(
                case=case,
                recorded_at=self._build_recorded_at(day, point_index, rng),
                bp_systolic=values["bp_systolic"],
                bp_diastolic=values["bp_diastolic"],
                pr=values["pr"],
                spo2=values["spo2"],
                weight_kg=values["weight_kg"],
                hemoglobin=values["hemoglobin"],
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
                event_type=ActivityEventType.CALL,
                note=f"Call outcome logged: {call_log.get_outcome_display()}",
            )

    def handle(self, *args, **options):
        profile_name = options["profile"]
        count = options["count"] if options["count"] is not None else (12 if profile_name == "smoke" else 30)
        count = max(count, 1)
        reset = options["reset"]
        reset_all = options["reset_all"]
        yes_reset_all = options["yes_reset_all"]
        include_vitals = options["include_vitals"]
        include_rch_scenarios = options["include_rch_scenarios"]

        if reset and reset_all:
            raise CommandError("Use either --reset or --reset-all, not both.")

        ensure_default_departments()
        anc = DepartmentConfig.objects.get(name="ANC")
        surgery = DepartmentConfig.objects.get(name="Surgery")
        non_surgical = DepartmentConfig.objects.get(name="Medicine")

        if reset_all:
            self._require_reset_all_confirmation(yes_reset_all)
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
            lambda anc, surgery, non_surgical, today, kwargs, _: self.build_quick_entry_case(surgery, today, kwargs),
            lambda anc, surgery, non_surgical, today, kwargs, _: self.build_surgery_planned_case(surgery, today, kwargs),
            lambda anc, surgery, non_surgical, today, kwargs, _: self.build_non_surgical_overdue_case(non_surgical, today, kwargs),
        ]
        if include_rch_scenarios:
            named_builders.insert(1, lambda anc, surgery, non_surgical, today, kwargs, _: self.build_anc_rch_missing_case(anc, today, kwargs))

        for i in range(1, count + 1):
            mock_profile = self.mock_profiles[(i - 1) % len(self.mock_profiles)]
            uhid = self._build_uhid(mock_profile, i, today)
            if Case.objects.filter(uhid=uhid).exists():
                continue
            kwargs = self._base_case_kwargs(mock_profile, i, today, demo_user)

            if i <= len(named_builders):
                case, scenario = named_builders[i - 1](anc, surgery, non_surgical, today, kwargs, i)
            else:
                case, scenario = self.build_default_case(anc, surgery, non_surgical, today, kwargs, i)

            details_task = None
            if (case.metadata or {}).get("entry_mode") == "quick_entry":
                details_task = create_quick_entry_details_task(case, demo_user, due_date=case.review_date)
            tasks = build_default_tasks(case, demo_user)
            self.mutate_seeded_tasks(case, rng, today)
            CaseActivityLog.objects.create(
                case=case,
                user=demo_user,
                event_type=ActivityEventType.SYSTEM,
                note=(
                    f"Mock case seeded with scenario '{scenario}', "
                    f"{len(tasks)} starter task(s)"
                    + (f", and '{QUICK_ENTRY_DETAILS_TASK_TITLE}' follow-up task" if details_task else "")
                ),
            )

            self.seed_calls_for_case(case, demo_user, scenario, rng)
            if include_vitals:
                self.seed_vitals_for_case(case, demo_user, today, rng, profile_name)
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Seeding complete. Created {created} new cases. Total cases: {Case.objects.count()}"))
