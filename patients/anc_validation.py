"""Outcome invariants shared by interactive actions and supported imports."""
from datetime import date

from django.core.exceptions import ValidationError
from django.utils import timezone


def validate_anc_outcome(*, outcome, outcome_date, reason, destination, continue_follow_up):
    if not outcome:
        return  # Genuine legacy records have no recorded outcome.
    errors = {}
    if outcome not in {"delivery", "loss_to_follow_up", "referral", "other"}:
        errors["anc_outcome"] = "Choose a valid ANC outcome."
    if not isinstance(outcome_date, date):
        errors["anc_outcome_date"] = "An outcome date is required."
    elif outcome_date > timezone.localdate():
        errors["anc_outcome_date"] = "Outcome date cannot be in the future."
    if not isinstance(reason, str) or not reason.strip():
        errors["anc_outcome_reason"] = "A nonblank outcome reason is required."
    if outcome == "referral" and (not isinstance(destination, str) or not destination.strip()):
        errors["anc_referral_destination"] = "Enter the referral destination."
    if type(continue_follow_up) is not bool:
        errors["anc_continue_follow_up"] = "Choose explicitly whether follow-up continues."
    if errors:
        raise ValidationError(errors)
