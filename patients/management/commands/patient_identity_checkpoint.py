import hashlib
import os
import sys
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from patients.identity import identity_allocation_lock, identity_checkpoint, reconcile_identity_allocator
from patients.identity_recovery import (
    MAX_CHECKPOINT_BYTES, decode_identity_checkpoint, encode_identity_checkpoint, verify_patient_identities,
)


class Command(BaseCommand):
    help = "Export or carry forward a trusted outgoing issuance checkpoint before older-restore activation."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=("export", "apply"))
        parser.add_argument("--database", default="default")
        parser.add_argument("--output", help="New restricted checkpoint file, or - for an explicit pipe.")
        parser.add_argument("--input", help="Trusted outgoing checkpoint file, or - for an explicit pipe.")
        parser.add_argument("--expected-sha256", help="SHA-256 of the trusted outgoing checkpoint file.")

    def handle(self, *args, **options):
        using = options["database"]
        try:
            with identity_allocation_lock(using=using):
                if options["action"] == "export":
                    destination = options["output"]
                    if not destination:
                        raise CommandError("Export requires --output; keep checkpoints in restricted durable storage.")
                    verify_patient_identities(using=using)
                    raw = encode_identity_checkpoint(identity_checkpoint(using=using))
                    if destination == "-":
                        self.stdout.write(raw, ending="")
                    else:
                        # Exclusive creation avoids replacing the surviving latest checkpoint.
                        descriptor = os.open(Path(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                            stream.write(raw)
                            stream.flush()
                            os.fsync(stream.fileno())
                        self.stdout.write("IDENTITY_CHECKPOINT_EXPORTED")
                    return
                source, expected = options["input"], options["expected_sha256"]
                if not source or not expected or len(expected) != 64:
                    raise CommandError("Apply requires --input and independently verified --expected-sha256 from the outgoing checkpoint.")
                if source == "-":
                    raw = sys.stdin.buffer.read(MAX_CHECKPOINT_BYTES + 1)
                else:
                    with Path(source).open("rb") as stream:
                        raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise CommandError("Outgoing identity checkpoint SHA-256 mismatch.")
                checkpoint = decode_identity_checkpoint(raw)
                reconcile_identity_allocator(
                    using=using, minimum_high_water=checkpoint["high_water"], bindings=checkpoint["bindings"],
                )
                result = verify_patient_identities(using=using)
                self.stdout.write("IDENTITY_CHECKPOINT_APPLIED high_water={high_water}".format(**result))
        except (ValidationError, OSError) as exc:
            message = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Unable to read/write the restricted checkpoint file."
            raise CommandError(message) from exc
