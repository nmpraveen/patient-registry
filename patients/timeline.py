"""Bounded canonical case history shared by web and native readers."""

from django.db.models import Max, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import ActivityEventType


FILTERS = (("all", "All"), ("calls", "Calls"), ("tasks", "Tasks"),
           ("notes", "Notes"), ("clinical", "Clinical"))
PAGE_SIZE = 30


def timeline_page(case, *, filter_key="all", position=None, snapshot=None):
    """Return <=30 events after a stable composite key, reading <=31 per source."""
    if filter_key not in dict(FILTERS):
        raise ValueError("Invalid timeline filter.")
    calls = case.call_logs.select_related("staff_user", "task")
    activities = case.activity_logs.select_related("user", "task").exclude(event_type=ActivityEventType.CALL)
    task_note = Q(event_type=ActivityEventType.TASK, task_id__isnull=False) & (
        Q(note__contains="[Task:") | Q(note__startswith="Task note updated:")
    )
    if filter_key == "tasks":
        activities = activities.filter(event_type=ActivityEventType.TASK).exclude(task_note)
    elif filter_key == "notes":
        activities = activities.filter(Q(event_type=ActivityEventType.NOTE) | task_note)
    elif filter_key == "clinical":
        activities = activities.filter(event_type=ActivityEventType.SYSTEM)
    if snapshot is None:
        snapshot = {"call": calls.aggregate(value=Max("pk"))["value"] or 0,
                    "activity": activities.aggregate(value=Max("pk"))["value"] or 0}
    entries = []
    for source, rank, queryset, enabled in (
        ("call", 1, calls, filter_key in {"all", "calls"}),
        ("activity", 0, activities, filter_key != "calls"),
    ):
        if not enabled:
            continue
        queryset = queryset.filter(pk__lte=snapshot[source])
        if position:
            timestamp = parse_datetime(position["timestamp"])
            if timestamp is None or timezone.is_naive(timestamp):
                raise ValueError("Invalid timeline position.")
            boundary = Q(created_at__lt=timestamp)
            if rank < position["rank"]:
                boundary |= Q(created_at=timestamp)
            elif rank == position["rank"]:
                boundary |= Q(created_at=timestamp, pk__lt=position["pk"])
            queryset = queryset.filter(boundary)
        for record in queryset.order_by("-created_at", "-pk")[:PAGE_SIZE + 1]:
            if source == "call":
                event_type, label = "CALL", "Call"
                actor = record.staff_user
                headline, reason, details = record.get_outcome_display(), record.reason, record.notes
            else:
                is_note = record.event_type == ActivityEventType.NOTE or (
                    record.event_type == ActivityEventType.TASK and record.task_id and
                    ("[Task:" in record.note or record.note.startswith("Task note updated:"))
                )
                event_type = record.event_type
                label = "Note" if is_note else ("Clinical" if event_type == "SYSTEM" else record.get_event_type_display())
                actor, headline, reason, details = record.user, record.note, "", ""
            entries.append({
                "id": f"{source}:{record.pk}", "event_type": event_type, "event_label": label,
                "timestamp": record.created_at, "actor": str(actor) if actor else "system",
                "task_title": record.task.title if record.task_id else "",
                "headline": headline, "reason": reason, "details": details,
                "_rank": rank, "_pk": record.pk,
            })
    entries.sort(key=lambda item: (item["timestamp"], item["_rank"], item["_pk"]), reverse=True)
    more = len(entries) > PAGE_SIZE
    entries = entries[:PAGE_SIZE]
    next_position = None
    if more:
        last = entries[-1]
        next_position = {"timestamp": last["timestamp"].isoformat(), "rank": last["_rank"], "pk": last["_pk"]}
    for entry in entries:
        entry.pop("_rank")
        entry.pop("_pk")
    return entries, next_position, snapshot
