import re
from datetime import datetime

from django.utils import timezone


QUOTED_COST_COMMAND_PREFIX = "CHR:"
QUOTED_COST_METADATA_KEY = "quoted_cost"
QUOTED_COST_ACTIVITY_NOTE = "Quoted cost reference updated."
QUOTED_COST_SUCCESS_MESSAGE = "Saved."
QUOTED_COST_HELP_TEXT = "Use CHR: 35 AI or CHR: 18-19 EX."
_QUOTED_COST_PATTERN = re.compile(
    r"^\s*(?P<amount_min>\d+)\s*(?:[kK])?\s*(?:-\s*(?P<amount_max>\d+)\s*(?:[kK])?)?\s+(?P<coverage>AI|EX)\s*$",
    re.IGNORECASE,
)


class QuotedCostParseError(ValueError):
    pass


def is_quoted_cost_command(note_text):
    return str(note_text or "").lstrip().upper().startswith(QUOTED_COST_COMMAND_PREFIX)


def extract_quoted_cost_payload(note_text):
    if not is_quoted_cost_command(note_text):
        return None
    return str(note_text or "").split(":", 1)[1].strip()


def _normalize_quoted_cost_payload(payload_text):
    payload = str(payload_text or "").strip()
    match = _QUOTED_COST_PATTERN.fullmatch(payload)
    if not match:
        raise QuotedCostParseError(QUOTED_COST_HELP_TEXT)

    amount_min = int(match.group("amount_min"))
    amount_max = int(match.group("amount_max") or amount_min)
    if amount_min < 1 or amount_max < 1:
        raise QuotedCostParseError(QUOTED_COST_HELP_TEXT)
    if amount_max < amount_min:
        raise QuotedCostParseError("Quoted cost range must increase from low to high.")

    normalized_range = str(amount_min) if amount_min == amount_max else f"{amount_min}-{amount_max}"
    coverage = match.group("coverage").upper()
    return {
        "amount_min_k": amount_min,
        "amount_max_k": amount_max,
        "coverage": coverage,
        "normalized_input": f"{normalized_range} {coverage}",
        "normalized_range": normalized_range,
    }


def parse_quoted_cost_payload(payload_text):
    normalized = _normalize_quoted_cost_payload(payload_text)
    return {
        "amount_min_k": normalized["amount_min_k"],
        "amount_max_k": normalized["amount_max_k"],
        "coverage": normalized["coverage"],
        "raw_input": normalized["normalized_input"],
    }


def build_quoted_cost_metadata(payload_text, *, user=None, recorded_at=None, now=None):
    normalized = _normalize_quoted_cost_payload(payload_text)
    recorded_local = timezone.localtime(recorded_at or now or timezone.now())
    return {
        "canonical_code": f"{recorded_local:%d-%m-%y}|{recorded_local:%H:%M}|{normalized['normalized_range']}|{normalized['coverage']}",
        "amount_min_k": normalized["amount_min_k"],
        "amount_max_k": normalized["amount_max_k"],
        "coverage": normalized["coverage"],
        "raw_input": normalized["normalized_input"],
        "updated_at": recorded_local.isoformat(),
        "updated_by_id": getattr(user, "pk", None) if user is not None else None,
    }


def parse_quoted_cost_command(note_text, *, recorded_at=None, updated_by_id=None):
    payload = extract_quoted_cost_payload(note_text)
    if payload is None:
        raise QuotedCostParseError(QUOTED_COST_HELP_TEXT)
    quoted_cost = build_quoted_cost_metadata(payload, recorded_at=recorded_at)
    quoted_cost["updated_by_id"] = updated_by_id
    return quoted_cost


def get_quoted_cost_metadata(metadata):
    if not isinstance(metadata, dict):
        return None
    quoted_cost = metadata.get(QUOTED_COST_METADATA_KEY)
    if not isinstance(quoted_cost, dict):
        return None
    return quoted_cost


def update_quoted_cost_metadata(metadata, quoted_cost):
    return {
        **(metadata or {}),
        QUOTED_COST_METADATA_KEY: quoted_cost,
    }


def get_quoted_cost_record(metadata_source):
    if hasattr(metadata_source, "metadata"):
        metadata_source = metadata_source.metadata
    quoted_cost = get_quoted_cost_metadata(metadata_source)
    if not quoted_cost:
        return None

    canonical_code = str(quoted_cost.get("canonical_code") or "").strip()
    raw_input = str(quoted_cost.get("raw_input") or "").strip()
    coverage = str(quoted_cost.get("coverage") or "").strip().upper()
    if not canonical_code or not raw_input or coverage not in {"AI", "EX"}:
        return None

    updated_at = quoted_cost.get("updated_at")
    updated_at_value = None
    if updated_at:
        try:
            updated_at_value = datetime.fromisoformat(str(updated_at))
        except ValueError:
            updated_at_value = None
        else:
            if timezone.is_naive(updated_at_value):
                updated_at_value = timezone.make_aware(updated_at_value, timezone.get_current_timezone())
            updated_at_value = timezone.localtime(updated_at_value)

    amount_min = quoted_cost.get("amount_min_k")
    amount_max = quoted_cost.get("amount_max_k")
    if amount_min is None or amount_max is None:
        normalized_range = raw_input.split(" ", 1)[0]
    else:
        normalized_range = str(amount_min) if amount_min == amount_max else f"{amount_min}-{amount_max}"
    display_timestamp = ""
    if updated_at_value is not None:
        display_timestamp = updated_at_value.strftime("%d%m%y%H%M")

    return {
        "canonical_code": canonical_code,
        "amount_min_k": amount_min,
        "amount_max_k": amount_max,
        "coverage": coverage,
        "raw_input": raw_input,
        "display_code": f"{display_timestamp}.{normalized_range}.{coverage}" if display_timestamp else f"{normalized_range}.{coverage}",
        "updated_at": updated_at_value,
        "updated_by_id": quoted_cost.get("updated_by_id"),
    }
