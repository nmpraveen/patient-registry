from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.throttling import BaseThrottle

from patients.audit import record_audit_event
from patients.models import AuditEvent, AuthenticationThrottleBucket
from patients.views import role_data_scope_payload


class DatabaseSearchThrottle(BaseThrottle):
    """Shared 30/minute account throttle; no process-local cache is involved."""

    rate_limit = 30
    window = timedelta(minutes=1)

    def _scope(self, view):
        return getattr(view, "database_throttle_scope", "api_search")[:24]

    def _key_hash(self, request, view):
        actor_id = getattr(request.user, "pk", None) or "anonymous"
        return salted_hmac(
            f"api.database_throttle.{self._scope(view)}",
            str(actor_id),
        ).hexdigest()

    def allow_request(self, request, view):
        now = timezone.now()
        scope = self._scope(view)
        with transaction.atomic():
            stale_ids = list(
                AuthenticationThrottleBucket.objects.filter(
                    scope=scope,
                    updated_at__lt=now - timedelta(days=1),
                )
                .order_by("updated_at", "pk")
                .values_list("pk", flat=True)[:100]
            )
            if stale_ids:
                AuthenticationThrottleBucket.objects.filter(pk__in=stale_ids).delete()
            bucket, _ = AuthenticationThrottleBucket.objects.select_for_update().get_or_create(
                scope=scope,
                key_hash=self._key_hash(request, view),
                defaults={"window_started_at": now},
            )
            if now - bucket.window_started_at >= self.window:
                bucket.failure_count = 0
                bucket.window_started_at = now
                bucket.blocked_until = None
            allowed = bucket.failure_count < self.rate_limit
            if allowed:
                bucket.failure_count += 1
            else:
                bucket.blocked_until = bucket.window_started_at + self.window
            bucket.save(
                update_fields=["failure_count", "window_started_at", "blocked_until", "updated_at"]
            )
        self.wait_seconds = max(
            1,
            int((bucket.window_started_at + self.window - now).total_seconds()) + 1,
        )
        if not allowed:
            self._audit_throttled(request, view)
        return allowed

    def wait(self):
        return self.wait_seconds

    def _audit_throttled(self, request, view):
        raw_query = request.data.get("query", "") if isinstance(request.data, dict) else ""
        normalized_length = len(" ".join(raw_query.split())) if isinstance(raw_query, str) else 0
        record_audit_event(
            category=AuditEvent.Category.DATA,
            action=getattr(view, "search_audit_action", "directory.search_attempt"),
            outcome=AuditEvent.Outcome.DENIED,
            actor=request.user if getattr(request.user, "is_authenticated", False) else None,
            request=request,
            object_type=getattr(view, "search_object_type", "directory"),
            metadata={
                "search_class": "throttled",
                "normalized_length": normalized_length,
                "result_count": 0,
                "scope": role_data_scope_payload(request.user)
                if getattr(request.user, "is_authenticated", False)
                else {},
            },
        )
