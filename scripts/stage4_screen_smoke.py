"""Synthetic Stage 4 screen acceptance; reuse the CI Playwright runtime."""

import argparse
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", type=int, required=True, help="Case seeded with --screen-scenarios")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="output/stage-4/browser")
    parser.add_argument("--save-only", action="store_true", help="Recheck only the synthetic save flow")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    receipts = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(args.base_url + "/login/")
        page.locator('[name="username"]').fill(os.environ.get("E2E_USERNAME", "demo_admin"))
        page.locator('[name="password"]').fill(os.environ["E2E_PASSWORD"])
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/patients/")
        for width in (() if args.save_only else (320, 390, 430, 1440)):
            page.set_viewport_size({"width": width, "height": 1000})
            for route, name in (("/patients/", "upcoming"),
                                (f"/patients/cases/{args.case_id}/", "case"),
                                ("/patients/cases/new/", "intake")):
                response = page.goto(args.base_url + route, wait_until="networkidle")
                assert response.status == 200, (route, response.status)
                fit = page.evaluate("""() => ({width: document.documentElement.clientWidth,
                    scroll: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)})""")
                assert fit["scroll"] <= fit["width"] + 1, (width, route, fit)
                if name == "upcoming":
                    expect(page.locator(".upcoming-date-group")).to_have_count(7)
                    summary = page.locator(".upcoming-compact-row summary").first
                    summary.focus()
                    page.keyboard.press("Enter")
                    expect(summary.locator("..")).to_have_attribute("open", "")
                    expect(page.locator(".upcoming-date-groups")).to_contain_text("Synthetic review")
                    page.locator("[data-upcoming-schedule]").screenshot(path=str(output / f"{width}-upcoming.png"))
                    page.get_by_role("link", name="Later dates", exact=True).click()
                    expect(page.locator(".upcoming-date-groups")).to_contain_text("Synthetic later visit")
                    page.get_by_role("link", name="Next 7 days", exact=True).click()
                    expect(page.locator(".upcoming-date-groups")).to_contain_text("Synthetic day seven")
                elif name == "case":
                    timeline = page.locator("#clinical-timeline")
                    expect(page.locator("#clinical-timeline-body")).to_be_visible()
                    expect(page.locator(".timeline-item")).to_have_count(30)
                    first_ids = page.locator(".timeline-item").evaluate_all("items => items.map(x => x.dataset.eventId)")
                    page.get_by_role("link", name="Older entries", exact=True).click()
                    second_ids = page.locator(".timeline-item").evaluate_all("items => items.map(x => x.dataset.eventId)")
                    assert not set(first_ids) & set(second_ids)
                    page.get_by_role("link", name="Latest entries", exact=True).click()
                    for label in ("Calls", "Tasks", "Notes", "Clinical", "All"):
                        page.locator("#clinical-timeline").get_by_role("link", name=label, exact=True).click()
                        expect(page.locator("#clinical-timeline-body")).to_be_visible()
                        if label == "Calls":
                            expect(timeline).to_contain_text("Synthetic general follow-up")
                        elif label == "Tasks":
                            expect(timeline).to_contain_text("Synthetic task created")
                        elif label == "Notes":
                            expect(timeline).to_contain_text("Synthetic timeline note")
                    page.locator(".log-jump").click()
                    expect(timeline).to_be_focused()
                    timeline.screenshot(path=str(output / f"{width}-timeline.png"))
                    page.screenshot(path=str(output / f"{width}-case.png"), full_page=True)
                else:
                    expect(page.locator("[data-case-submit-button]")).to_have_count(1)
                    optional = page.locator("details.case-create-optional")
                    assert optional.get_attribute("open") is None
                    optional.locator("summary").focus()
                    page.keyboard.press("Enter")
                    expect(optional).to_have_attribute("open", "")
                    page.locator('[name="first_name"]').fill("Synthetic draft")
                    page.locator('[name="notes"]').fill("Synthetic optional draft retained")
                    page.get_by_role("button", name="Save Case", exact=True).click()
                    expect(page.locator('[name="first_name"]')).to_have_value("Synthetic draft")
                    expect(page.locator('[name="notes"]')).to_have_value("Synthetic optional draft retained")
                    assert page.locator(".invalid-feedback:visible").count() > 0
                    page.screenshot(path=str(output / f"{width}-intake-validation.png"), full_page=True)
                    # A dirty form warns and dismissal keeps the draft on the current page.
                    page.once("dialog", lambda dialog: dialog.dismiss())
                    page.get_by_role("link", name="Cancel", exact=True).click()
                    expect(page.locator('[name="first_name"]')).to_have_value("Synthetic draft")
                    page.once("dialog", lambda dialog: dialog.accept())
                    page.get_by_role("link", name="Cancel", exact=True).click()
                    page.wait_for_url("**/patients/")
                print("PASS", width, name, flush=True)
                receipts.append({"viewport": width, "screen": name, "fit": fit, "result": "PASS"})

        # Exercise the unchanged final save path once, with a new synthetic identity.
        page.goto(args.base_url + "/patients/cases/new/", wait_until="networkidle")
        page.locator("label.case-create-choice").filter(has_text="Medicine").click()
        expect(page.locator('[name="review_frequency"]')).to_be_visible()
        page.locator('[name="subcategory"]').select_option("GENERAL_MEDICINE")
        page.locator('[name="uhid"]').fill("")  # Stage 3 optional hospital ID; server allocates MTNO.
        page.locator('[name="prefix"]').select_option("MR")
        page.locator('[name="first_name"]').fill("Synthetic")
        page.locator('[name="last_name"]').fill("Screen acceptance")
        page.locator('[name="age"]').fill("35")
        page.locator('[name="phone_number"]').fill("9000011134")
        page.locator('[name="diagnosis"]').fill("Synthetic follow-up")
        page.locator('[name="review_frequency"]').select_option("MONTHLY")
        picker = page.locator('fw-datepicker[data-crayons-datepicker-for="id_review_date"] input:visible').first
        picker.fill((date.today() + timedelta(days=2)).strftime("%d/%m/%Y"))
        picker.press("Tab")
        page.locator("details.case-create-optional summary").click()
        page.locator('[name="notes"]').fill("Synthetic final save proof")
        page.get_by_role("button", name="Save Case", exact=True).click()
        page.wait_for_url(re.compile(r"/patients/cases/\d+/$"), timeout=15000)
        expect(page.locator(".case-detail-title")).to_contain_text(re.compile("Screen acceptance", re.I))
        receipts.append({"screen": "intake-save", "result": "PASS", "path": page.url.split(args.base_url)[-1]})
        (output / ("save-receipt.json" if args.save_only else "receipt.json")).write_text(json.dumps(receipts, indent=2), encoding="utf-8")
        browser.close()
    print("STAGE4_SCREEN_SMOKE_PASS", len(receipts))


if __name__ == "__main__":
    main()
