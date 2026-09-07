"""Synthetic Stage 1 UI smoke. Run only on a local seeded scratch database."""
import os
from pathlib import Path
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patient_registry.settings")
import django
django.setup()

from django.utils import timezone
from patients.models import Case
from playwright.sync_api import sync_playwright


def main():
    output = Path("output/playwright/issue113-stage1")
    output.mkdir(parents=True, exist_ok=True)
    case = Case.objects.get(metadata__seed_case_key__startswith="edd_overdue:")
    base = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")
    assert base.startswith(("http://127.0.0.1:", "http://localhost:")), "Synthetic local smoke only"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + "/login/")
        page.locator('[name="username"]').fill("demo_admin")
        page.locator('[name="password"]').fill(os.environ["E2E_PASSWORD"])
        page.locator('button[type="submit"]').click()
        page.wait_for_url(base + "/patients/")
        for width in (320, 390, 430, 1440):
            page.set_viewport_size({"width": width, "height": 1000})
            for label, path in (
                ("dashboard", "/patients/"), ("dormant", "/patients/follow-up/?bucket=dormant"),
                ("overdue", "/patients/follow-up/?bucket=overdue"), ("missing", "/patients/follow-up/?bucket=edd_missing"),
                ("anc", f"/patients/cases/{case.pk}/anc/"),
            ):
                response = page.goto(base + path, wait_until="networkidle")
                assert response.status == 200, (path, response.status)
                assert page.evaluate("Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) <= document.documentElement.clientWidth + 1"), (width, path)
                if label in ("anc", "dormant", "overdue") and width in (390, 1440):
                    page.screenshot(path=str(output / f"{label}-{width}.png"), full_page=True)
        page.locator('[name="action"]').select_option("correct_edd")
        page.locator('[name="usg_edd"]').fill((timezone.localdate() + timedelta(days=20)).isoformat())
        page.locator('[name="reason"]').fill("Synthetic USG date correction")
        page.get_by_role("button", name="Save ANC action").click()
        page.wait_for_url(base + f"/patients/cases/{case.pk}/")
        assert page.get_by_text("Dormant", exact=True).count() >= 1
        page.get_by_role("link", name="ANC outcome / EDD correction").click()
        page.locator('[name="outcome"]').select_option("referral")
        page.locator('[name="outcome_date"]').fill(timezone.localdate().isoformat())
        page.locator('[name="referral_destination"]').fill("Synthetic referral clinic")
        page.locator('[name="continue_follow_up"]').select_option("continue")
        page.locator('[name="reason"]').fill("Synthetic continuing referral")
        page.get_by_role("button", name="Save ANC action").click()
        page.wait_for_url(base + f"/patients/cases/{case.pk}/")
        page.screenshot(path=str(output / "referral-recorded-1440.png"), full_page=True)
        browser.close()
    case.refresh_from_db()
    assert not case.follow_up["edd_overdue"]
    assert case.anc_outcome == "referral" and case.anc_continue_follow_up
    print("STAGE1_UI_SMOKE_OK 5 routes x 4 widths; EDD correction and continuing referral persisted")


if __name__ == "__main__":
    main()
