"""Clock-boundary regressions for synthetic vital timestamps."""

from datetime import datetime, timedelta
from random import Random
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from .management.commands.seed_mock_data import Command


@override_settings(TIME_ZONE="Asia/Kolkata")
class SeedVitalTimestampTests(SimpleTestCase):
    def test_today_keeps_its_scheduled_date_without_future_timestamps(self):
        for hour, minute in ((0, 0), (0, 3), (0, 5), (8, 0), (15, 0)):
            now = timezone.make_aware(datetime(2026, 1, 1, hour, minute))
            with self.subTest(now=now), patch(
                "patients.management.commands.seed_mock_data.timezone.now", return_value=now
            ):
                recorded_at = Command()._build_recorded_at(now.date(), 0, Random(42))
                self.assertLessEqual(recorded_at, now)
                self.assertEqual(timezone.localdate(recorded_at), now.date())

    def test_past_dates_keep_their_scheduled_day_and_clinic_time(self):
        now = timezone.make_aware(datetime(2026, 1, 1, 0, 3))
        for age in (1, 7):
            day = now.date() - timedelta(days=age)
            with self.subTest(day=day), patch(
                "patients.management.commands.seed_mock_data.timezone.now", return_value=now
            ):
                recorded_at = Command()._build_recorded_at(day, 0, Random(42))
                self.assertLess(recorded_at, now)
                local = timezone.localtime(recorded_at)
                self.assertEqual(local.date(), day)
                self.assertGreaterEqual(local.hour, 8)
                self.assertLessEqual(local.hour, 14)
