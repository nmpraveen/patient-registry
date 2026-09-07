"""Read-only inventory for human reconciliation; never reopen historical cases."""
import csv

from django.core.management.base import BaseCommand

from patients.models import Case, CaseStatus


class Command(BaseCommand):
    help = "Read-only CSV of closed ANC cases without a recorded outcome. No patient names or contact details."

    def handle(self, *args, **options):
        writer = csv.writer(self.stdout)
        writer.writerow(["case_id", "patient_id", "status", "archived", "effective_edd"])
        for case in Case.objects.filter(category__name__iexact="ANC", anc_outcome="").exclude(
            status=CaseStatus.ACTIVE
        ).order_by("pk").iterator():
            writer.writerow([case.pk, case.patient_id or "", case.status, case.is_archived, case.effective_edd or ""])
