from pathlib import Path

from django.core.management.base import BaseCommand

from patients import database_bundle


class Command(BaseCommand):
    help = "Create a manual patient-data backup ZIP bundle and prune older manual bundles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="",
            help="Directory where patient-data backup bundles should be written.",
        )
        parser.add_argument(
            "--keep",
            type=int,
            default=database_bundle.DEFAULT_BACKUP_KEEP,
            help="Number of newest manual backup bundles to keep after writing the new backup.",
        )

    def handle(self, *args, **options):
        output_dir = options["output_dir"].strip() or None
        if output_dir:
            output_dir = Path(output_dir)

        bundle_path, manifest, pruned = database_bundle.write_backup_bundle(
            output_dir=output_dir,
            keep=options["keep"],
        )
        counts = manifest["counts"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Created patient-data backup at {bundle_path} "
                f"({counts['cases']} cases, {counts['tasks']} tasks, {counts['vitals']} vitals)."
            )
        )
        if pruned:
            self.stdout.write(
                f"Pruned {len(pruned)} older backup bundle(s) from {bundle_path.parent}."
            )
