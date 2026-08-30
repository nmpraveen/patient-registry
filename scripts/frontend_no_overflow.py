#!/usr/bin/env python3
"""Authenticated document-overflow smoke test using synthetic seeded data only."""

from __future__ import annotations

import argparse
import os
import re
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright


VIEWPORTS = (320, 390, 430, 1440)
STATIC_ROUTES = (
    "/patients/",
    "/patients/cases/",
    "/patients/patients/",
    "/patients/calls/upcoming/",
)


def document_width(page: Page) -> tuple[int, int]:
    return page.evaluate(
        """() => [
            Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0),
            document.documentElement.clientWidth
        ]"""
    )


def overflowing_elements(page: Page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('body *'))
          .filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.right > document.documentElement.clientWidth + 1 || rect.left < -1;
          })
          .slice(0, 8)
          .map((element) => {
            const id = element.id ? `#${element.id}` : '';
            const classes = Array.from(element.classList || []).slice(0, 3).map((c) => `.${c}`).join('');
            return `${element.tagName.toLowerCase()}${id}${classes}`;
          })"""
    )


def discover_detail_routes(page: Page) -> list[str]:
    hrefs = page.locator("a[href]").evaluate_all(
        "elements => elements.map((element) => element.getAttribute('href')).filter(Boolean)"
    )
    routes: list[str] = []
    for pattern in (r"^/patients/cases/\d+/$", r"^/patients/patients/\d+/$"):
        match = next((href for href in hrefs if re.match(pattern, href)), None)
        if match:
            routes.append(match)
    return routes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000"))
    args = parser.parse_args()
    username = os.environ.get("E2E_USERNAME", "demo_admin")
    password = os.environ.get("E2E_PASSWORD")
    if not password:
        raise SystemExit("E2E_PASSWORD must contain the synthetic seeded-user password")
    failures: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        response = page.goto(urljoin(args.base_url, "/login/"), wait_until="networkidle")
        if response is None or response.status >= 400:
            raise SystemExit("login page was unavailable")
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"], input[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")
        if "/login/" in page.url:
            raise SystemExit("synthetic test-user login failed")

        page.goto(urljoin(args.base_url, "/patients/cases/"), wait_until="networkidle")
        routes = list(STATIC_ROUTES) + discover_detail_routes(page)
        if len(routes) != len(STATIC_ROUTES) + 2:
            failures.append("seeded case and patient detail routes were not both discoverable")

        for width in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": 1000})
            for route in routes:
                response = page.goto(urljoin(args.base_url, route), wait_until="networkidle")
                if response is None or response.status >= 400:
                    failures.append(f"HTTP failure width={width} route={route}")
                    continue
                scroll_width, client_width = document_width(page)
                if scroll_width > client_width + 1:
                    offenders = ", ".join(overflowing_elements(page)) or "unknown"
                    failures.append(
                        f"overflow width={width} route={route} "
                        f"scroll={scroll_width} client={client_width} elements={offenders}"
                    )
        browser.close()

    if failures:
        for failure in failures:
            print(f"FRONTEND_OVERFLOW_FAIL {failure}")
        return 1
    print(f"FRONTEND_NO_OVERFLOW_OK routes={len(routes)} viewports={len(VIEWPORTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
