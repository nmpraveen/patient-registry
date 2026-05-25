from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.notifications import notify_task_overdue
from patients.models import Task, TaskStatus


class Command(BaseCommand):
    help = "Create mobile notifications for assigned overdue MEDTRACK tasks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            help="Business date in YYYY-MM-DD format. Defaults to the local Django date.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count eligible overdue tasks without creating notifications.",
        )

    def handle(self, *args, **options):
        as_of = timezone.localdate()
        if options.get("date"):
            as_of = datetime.strptime(options["date"], "%Y-%m-%d").date()

        tasks = (
            Task.objects.select_related("case", "assigned_user")
            .filter(assigned_user__isnull=False, due_date__lt=as_of)
            .exclude(status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED])
            .order_by("due_date", "id")
        )
        eligible_count = tasks.count()
        created_count = 0
        if not options["dry_run"]:
            for task in tasks:
                before_id = notify_task_overdue(task, as_of=as_of)
                if before_id:
                    created_count += 1

        if options["dry_run"]:
            self.stdout.write(f"{eligible_count} overdue task(s) eligible for mobile notification.")
        else:
            self.stdout.write(f"Processed {eligible_count} overdue task(s); {created_count} notification row(s) present.")
