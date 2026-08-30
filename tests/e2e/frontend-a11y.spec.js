const fs = require("node:fs");
const path = require("node:path");
const { expect, test } = require("@playwright/test");

const username = process.env.PLAYWRIGHT_USERNAME || "a11y-admin";
const password = process.env.PLAYWRIGHT_PASSWORD || "a11y-test-password";
const screenshotDir = path.resolve("output/playwright/screenshots");

fs.mkdirSync(screenshotDir, { recursive: true });

async function login(page) {
  await page.goto("/login/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await Promise.all([
    page.waitForURL(/\/patients\/$/),
    page.getByRole("button", { name: /log in|sign in/i }).click(),
  ]);
}

async function firstHref(page, selector) {
  const locator = page.locator(selector).first();
  await expect(locator).toHaveAttribute("href", /\/$/);
  return locator.getAttribute("href");
}

async function expectNoHorizontalDocumentOverflow(page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
}

test.beforeEach(async ({ page }, testInfo) => {
  testInfo.errorsFromPage = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      testInfo.errorsFromPage.push(`console: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => testInfo.errorsFromPage.push(`pageerror: ${error.message}`));
  page.on("requestfailed", (request) => {
    testInfo.errorsFromPage.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText || ""}`);
  });
  await login(page);
});

test.afterEach(async ({}, testInfo) => {
  expect(testInfo.errorsFromPage, testInfo.errorsFromPage.join("\n")).toEqual([]);
});

test("case and patient detail layouts do not overflow the required viewport", async ({ page }, testInfo) => {
  await page.goto("/patients/cases/");
  const caseHref = await firstHref(page, 'tbody a[href^="/patients/cases/"]');
  await page.goto(caseHref);
  await expect(page.getByTestId("case-detail-shell")).toBeVisible();
  await expectNoHorizontalDocumentOverflow(page);
  const taskActionBoxes = await page.locator(".case-task-card__actions .case-task-action:visible").evaluateAll((buttons) => (
    buttons.map((button) => {
      const bounds = button.getBoundingClientRect();
      return { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom };
    })
  ));
  for (let leftIndex = 0; leftIndex < taskActionBoxes.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < taskActionBoxes.length; rightIndex += 1) {
      const left = taskActionBoxes[leftIndex];
      const right = taskActionBoxes[rightIndex];
      const overlaps = left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top;
      expect(overlaps).toBe(false);
    }
  }

  if (["chromium-320", "chromium-desktop"].includes(testInfo.project.name)) {
    await page.screenshot({
      path: path.join(screenshotDir, `case-detail-${testInfo.project.name}.png`),
      fullPage: true,
    });
  }

  await page.goto("/patients/patients/");
  const patientHref = await firstHref(page, 'tbody a[href^="/patients/patients/"]');
  await page.goto(patientHref);
  await expectNoHorizontalDocumentOverflow(page);

  const mergeSelect = page.getByLabel("Merge into patient");
  await expect(mergeSelect).toBeVisible();
  const selectBounds = await mergeSelect.boundingBox();
  const viewport = page.viewportSize();
  expect(selectBounds.x).toBeGreaterThanOrEqual(0);
  expect(selectBounds.x + selectBounds.width).toBeLessThanOrEqual(viewport.width + 1);
});

test("universal search exposes keyboard-operable combobox and live state", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Semantic interaction is covered once at desktop width.");

  await page.goto("/patients/");
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
  await expect(page.locator(".skip-link")).toBeVisible();

  const search = page.getByRole("combobox", { name: "Search patients or cases" });
  await expect(search).toHaveAttribute("aria-autocomplete", "list");
  await expect(search).toHaveAttribute("aria-expanded", "false");
  await search.fill("Mock");
  const listbox = page.getByRole("listbox", { name: "Patient and case search results" });
  await expect(listbox).toBeVisible();
  await expect(search).toHaveAttribute("aria-expanded", "true");
  await search.press("ArrowDown");
  const activeId = await search.getAttribute("aria-activedescendant");
  expect(activeId).toBeTruthy();
  await expect(page.locator(`#${activeId}`)).toHaveAttribute("role", "option");
  await expect(page.locator(`#${activeId}`)).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#global-search-status")).not.toHaveText("");
  await search.press("Escape");
  await expect(search).toHaveAttribute("aria-expanded", "false");
});

test("form IDs and call-sheet selections expose unique accessible names", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "DOM semantics are covered once at desktop width.");

  await page.goto("/patients/settings/users/?tab=users");
  const userFormIds = await page.locator('[id^="id_user-"]').evaluateAll((nodes) => nodes.map((node) => node.id));
  expect(userFormIds.length).toBeGreaterThan(0);
  expect(new Set(userFormIds).size).toBe(userFormIds.length);
  expect(userFormIds).toContain("id_user-create-first_name");
  expect(userFormIds).toContain("id_user-edit-first_name");

  await page.goto("/patients/settings/users/?tab=roles");
  const roleFormIds = await page.locator('[id^="id_role-"]').evaluateAll((nodes) => nodes.map((node) => node.id));
  expect(roleFormIds.length).toBeGreaterThan(0);
  expect(new Set(roleFormIds).size).toBe(roleFormIds.length);
  expect(roleFormIds).toContain("id_role-create-role_name");
  expect(roleFormIds).toContain("id_role-edit-role_name");

  await page.goto("/patients/calls/upcoming/");
  const selections = page.locator('input[name="case_ids"]');
  expect(await selections.count()).toBeGreaterThan(0);
  for (let index = 0; index < await selections.count(); index += 1) {
    const input = selections.nth(index);
    const inputId = await input.getAttribute("id");
    const label = page.locator(`label[for="${inputId}"]`);
    await expect(label).toHaveText(/Select .+, UHID .+, case \d+/);
  }
});

test("merge review names both UHIDs, affected cases, and stays within its container", async ({ page }, testInfo) => {
  test.skip(!["chromium-320", "chromium-desktop"].includes(testInfo.project.name), "Merge evidence is captured at the narrowest and desktop widths.");

  await page.goto("/patients/patients/");
  const patientHref = await firstHref(page, 'tbody a[href^="/patients/patients/"]');
  await page.goto(patientHref);
  const mergeSelect = page.getByLabel("Merge into patient");
  await mergeSelect.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Review Merge" }).click();
  await expect(page.getByRole("heading", { name: "Review Patient Merge" })).toBeVisible();
  await expect(page.getByText("Source UHID", { exact: true })).toBeVisible();
  await expect(page.getByText("Target UHID", { exact: true })).toBeVisible();
  await expect(page.getByText("Affected cases", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Type target UHID to confirm")).toBeVisible();
  await expectNoHorizontalDocumentOverflow(page);
  await page.screenshot({
    path: path.join(screenshotDir, `patient-merge-review-${testInfo.project.name}.png`),
    fullPage: true,
  });
});

test("CSP loads only local pinned assets and theme contrast preview remains active", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Asset and theme runtime checks are covered once at desktop width.");
  const externalRequests = [];
  page.on("request", (request) => {
    if (request.url().startsWith("blob:")) {
      return;
    }
    const requestUrl = new URL(request.url());
    if (!requestUrl.href.startsWith(testInfo.project.use.baseURL || "http://127.0.0.1:8016")) {
      externalRequests.push(request.url());
    }
  });

  const response = await page.goto("/patients/cases/new/");
  const csp = response.headers()["content-security-policy"];
  expect(csp).toContain("script-src 'self' blob:");
  expect(csp).toContain("script-src-attr 'none'");
  await page.waitForFunction(() => customElements.get("fw-datepicker"));
  await expect(page.locator('script[src*="vendor/crayons/4.1.0"]')).toHaveCount(2);
  await expect(page.locator('script[src*="cdn.jsdelivr.net"]')).toHaveCount(0);

  await page.goto("/patients/settings/theme/");
  const contrastSummary = page.locator("[data-contrast-summary]");
  await expect(contrastSummary).toBeVisible();
  await expect(contrastSummary).toContainText(/contrast/i);
  const pageTextInput = page.locator('[name="shell__page_text"]');
  const pageBackground = await page.locator('[name="shell__page_bg"]').inputValue();
  await pageTextInput.fill(pageBackground);
  await expect(pageTextInput).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("[data-theme-save]")).toBeDisabled();
  expect(externalRequests).toEqual([]);
});

test("logout cannot reveal cached PHI with browser back", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Cache behavior is covered once at desktop width.");

  await page.goto("/patients/patients/");
  const patientHref = await firstHref(page, 'tbody a[href^="/patients/patients/"]');
  await page.goto(patientHref);
  const patientUrl = page.url();
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login\//);
  await page.goBack({ waitUntil: "domcontentloaded" });
  expect(page.url()).not.toBe(patientUrl);
  await expect(page).toHaveURL(/\/login\//);
  await expect(page.getByLabel("Username")).toBeVisible();
});
