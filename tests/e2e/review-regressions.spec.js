const { test, expect } = require("@playwright/test");

const username = process.env.PLAYWRIGHT_USERNAME || "a11y-admin";
const password = process.env.PLAYWRIGHT_PASSWORD || "a11y-test-password";

test.beforeEach(async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "State transitions are exercised once; responsive layout has its own matrix.");
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  testInfo.webErrors = errors;
  await page.goto("/login/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await Promise.all([
    page.waitForURL(/\/patients\/$/),
    page.getByRole("button", { name: /log in|sign in/i }).click(),
  ]);
});

test.afterEach(async ({}, testInfo) => {
  expect(testInfo.webErrors || []).toEqual([]);
});

async function openAncForm(page) {
  await page.goto("/patients/cases/new/");
  await page.getByRole("radio", { name: "ANC", exact: true }).check();
  await expect(page.locator("#id_gravida")).toBeAttached();
  await expect(page.locator("#case-create-shell-state")).toHaveAttribute("data-workflow-key", "anc");
}

test("a delayed intake preview cannot overwrite a newer GPAL value", async ({ page }) => {
  await openAncForm(page);
  await page.getByRole("button", { name: "Increase Gravida", exact: true }).click();
  let release;
  let requested;
  const captured = new Promise((resolve) => { requested = resolve; });
  let count = 0;
  const snapshots = [];
  await page.route("**/patients/cases/new/preview/", async (route) => {
    snapshots.push(route.request().postDataJSON());
    if (++count === 1) {
      const response = await route.fetch();
      requested();
      await new Promise((resolve) => { release = resolve; });
      await route.fulfill({ response });
    } else await route.continue();
  });
  await page.locator("#id_rch_number").fill("123456789");
  await page.locator("#id_rch_number").blur();
  await captured;
  await page.getByRole("button", { name: "Increase Gravida", exact: true }).click();
  release();
  await expect.poll(() => count).toBeGreaterThan(1);
  await expect(page.locator("#id_gravida")).toHaveValue("2");
  expect(snapshots[0].gravida).toBe("1");
  expect(snapshots.at(-1).gravida).toBe("2");
});

test("switching categories restores this category's cleared and unchecked draft", async ({ page }) => {
  await openAncForm(page);
  await page.getByRole("button", { name: "Increase Gravida", exact: true }).click();
  await page.locator("#id_rch_number").fill("");
  await page.getByRole("radio", { name: "Medicine", exact: true }).check();
  await expect(page.locator("#id_gravida")).toHaveCount(0);
  await page.getByRole("radio", { name: "ANC", exact: true }).check();
  await expect(page.locator("#id_gravida")).toHaveValue("1");
  await expect(page.locator("#id_rch_number")).toHaveValue("");
  await expect(page.locator("#id_high_risk")).not.toBeChecked();
});

test("clear and Escape cannot resurrect an in-flight patient search", async ({ page }) => {
  await page.goto("/patients/cases/new/");
  await page.locator('input[name="patient_mode"][value="existing"]').check();
  const input = page.locator("[data-patient-search-input]");
  for (const clear of ["button", "escape"]) {
    let release;
    let requested;
    let finished;
    const captured = new Promise((resolve) => { requested = resolve; });
    const fulfilled = new Promise((resolve) => { finished = resolve; });
    await page.route("**/patients/patients/search/**", async (route) => {
      requested();
      await new Promise((resolve) => { release = resolve; });
      try {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ results: [{ id: 123456, name: "STALE SYNTHETIC PATIENT" }] }) });
      } catch (error) {
        if (!String(error).includes("aborted")) throw error;
      } finally { finished(); }
    });
    await input.fill("Synthetic");
    await captured;
    if (clear === "button") await page.locator("[data-patient-search-clear]").click();
    else await input.press("Escape");
    release();
    await fulfilled;
    await expect(input).toHaveValue("");
    await expect(page.locator("[data-patient-search-results]")).toBeHidden();
    await expect(page.getByText("STALE SYNTHETIC PATIENT")).toHaveCount(0);
    await page.unroute("**/patients/patients/search/**");
  }
});

test("date labels identify the real editable inputs and validation focuses them", async ({ page }) => {
  await openAncForm(page);
  const lmp = page.getByRole("textbox", { name: "LMP", exact: true });
  const edd = page.getByRole("textbox", { name: "EDD", exact: true });
  await expect(lmp).toBeVisible();
  await expect(edd).toBeVisible();
  await page.locator('label[for="id_lmp"]').click();
  await expect(lmp).toBeFocused();
  await page.evaluate(() => window.medtrackCrayonsDatepicker.focusInput(document.getElementById("id_edd")));
  await expect(edd).toBeFocused();
});

test("recent notes fetch one case and keep an unsaved draft after an error", async ({ page }) => {
  await page.goto("/patients/");
  const row = page.locator("[data-recent-case-row]").first();
  const id = await row.getAttribute("data-case-id");
  const detailRequests = [];
  page.on("request", (request) => {
    if (/\/patients\/recent\//.test(request.url()) && request.method() === "GET") detailRequests.push(request.url());
  });
  await row.locator("[data-recent-case-trigger]").click();
  const notes = row.locator('textarea[name="notes"]');
  await expect(notes).toBeVisible();
  expect(detailRequests).toHaveLength(1);
  expect(new URL(detailRequests[0]).pathname).toBe(`/patients/recent/${id}/`);
  await expect(row.locator('input[name="diagnosis"]')).toHaveCount(0);
  await expect(row.locator('input[name="notes_baseline"]')).not.toHaveValue("");
  let body;
  await page.route(`**/patients/recent/${id}/`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    body = route.request().postData();
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ message: "Synthetic stale-note conflict" }) });
  });
  await notes.fill("Keep this unsaved synthetic note");
  await row.getByRole("button", { name: "Save notes", exact: true }).click();
  await expect(row.getByRole("status")).toContainText("Synthetic stale-note conflict");
  await expect(notes).toHaveValue("Keep this unsaved synthetic note");
  expect(body).toContain('name="notes_baseline"');
  expect(body).not.toContain('name="diagnosis"');
  await row.locator("[data-recent-case-trigger]").click();
  await row.locator("[data-recent-case-trigger]").click();
  await expect(notes).toHaveValue("Keep this unsaved synthetic note");
  expect(detailRequests).toHaveLength(1);
});

test("recent summaries load incrementally without duplicating rows or fetching every detail", async ({ page }) => {
  await page.goto("/patients/");
  const rows = page.locator("[data-recent-case-row]");
  await expect(rows).toHaveCount(20);
  await expect(page.locator("#recent-case-endpoints")).not.toHaveAttribute("data-next-cursor", "");
  const requests = [];
  page.on("request", (request) => {
    if (/\/patients\/recent\//.test(request.url())) requests.push(request.url());
  });
  await page.locator("[data-recent-case-toggle]").click();
  await page.getByRole("button", { name: "Load more", exact: true }).click();
  await expect.poll(() => rows.count()).toBeGreaterThan(20);
  const ids = await rows.evaluateAll((elements) => elements.map((element) => element.dataset.caseId));
  expect(new Set(ids).size).toBe(ids.length);
  expect(requests).toHaveLength(1);
  const request = new URL(requests[0]);
  expect(request.pathname).toBe("/patients/recent/");
  expect(request.searchParams.get("cursor")).toBeTruthy();
  expect(request.searchParams.get("limit")).toBe("20");
  await expect(rows.locator('textarea[name="notes"]')).toHaveCount(0);
});

test("an edit preview cannot replace clinical changes made while its response is pending", async ({ page }) => {
  await page.goto("/patients/cases/?category_group=anc");
  const detailUrl = await page.locator('tbody a[href^="/patients/cases/"]').first().getAttribute("href");
  await page.goto(`${detailUrl}edit/`);
  const gravida = page.locator("#id_gravida");
  const initial = Number(await gravida.inputValue());
  expect(initial).toBeLessThan(10);
  let release;
  let requested;
  const captured = new Promise((resolve) => { requested = resolve; });
  let count = 0;
  await page.route("**/edit/preview/", async (route) => {
    if (++count === 1) {
      const response = await route.fetch();
      requested();
      await new Promise((resolve) => { release = resolve; });
      await route.fulfill({ response });
    } else await route.continue();
  });
  await page.locator("#id_rch_number").fill("123456780");
  await page.locator("#id_rch_number").blur();
  await captured;
  await page.getByRole("button", { name: "Increase Gravida", exact: true }).click();
  release();
  await expect.poll(() => count).toBeGreaterThan(1);
  await expect(gravida).toHaveValue(String(initial + 1));
});

test("Escape cancels an edit autocomplete response before the suggestions become visible", async ({ page }) => {
  await page.goto("/patients/cases/");
  const detailUrl = await page.locator('tbody a[href^="/patients/cases/"]').first().getAttribute("href");
  await page.goto(`${detailUrl}edit/`);
  let release;
  let requested;
  let finished;
  const captured = new Promise((resolve) => { requested = resolve; });
  const fulfilled = new Promise((resolve) => { finished = resolve; });
  await page.route("**/patients/cases/autocomplete/**", async (route) => {
    requested();
    await new Promise((resolve) => { release = resolve; });
    try { await route.fulfill({ json: ["STALE EDIT SUGGESTION"] }); }
    catch (error) { if (!String(error).includes("aborted")) throw error; }
    finally { finished(); }
  });
  await page.locator("#id_place").fill("Synthetic");
  await captured;
  await page.locator("#id_place").press("Escape");
  release();
  await fulfilled;
  await expect(page.locator("#id_place-autocomplete")).toBeHidden();
  await expect(page.getByText("STALE EDIT SUGGESTION")).toHaveCount(0);
});

test("WebAuthn fallback serializes native registration and assertion credentials", async ({ page, context }) => {
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
  });
  await page.addInitScript(() => {
    Object.defineProperty(PublicKeyCredential.prototype, "toJSON", { value: undefined, configurable: true });
    Object.defineProperty(PublicKeyCredential, "parseCreationOptionsFromJSON", { value: undefined, configurable: true });
    Object.defineProperty(PublicKeyCredential, "parseRequestOptionsFromJSON", { value: undefined, configurable: true });
  });
  const challenge = Buffer.from("synthetic-browser-webauthn-challenge").toString("base64url");
  let registration;
  let assertion;
  // This browser-only harness exercises the shipped asset and native credentials
  // without creating or approving devices in the application database.
  await page.route("**/__synthetic_webauthn_review__/**", async (route) => {
    const endpoint = new URL(route.request().url()).pathname.split("/").filter(Boolean).at(-1);
    let payload;
    if (endpoint === "create-options") payload = {
      challenge, rp: { name: "Synthetic review" }, user: { id: "c3ludGhldGlj", name: "synthetic", displayName: "Synthetic" },
      pubKeyCredParams: [{ type: "public-key", alg: -7 }], timeout: 10000, attestation: "none",
      authenticatorSelection: { residentKey: "required", userVerification: "required" },
    };
    else if (endpoint === "create-verify") {
      registration = route.request().postDataJSON().credential;
      payload = { message: "Synthetic registration captured" };
    } else if (endpoint === "get-options") payload = {
      challenge, timeout: 10000, userVerification: "required", allowCredentials: [{ type: "public-key", id: registration.id }],
    };
    else if (endpoint === "get-verify") {
      assertion = route.request().postDataJSON().credential;
      return route.fulfill({ status: 400, json: { message: "Synthetic assertion captured" } });
    } else return route.fulfill({ contentType: "text/html", body: `<!doctype html><html><body>
      <div id="device-status" role="status"></div><input id="device-label" value="Synthetic browser">
      <button id="register-device-button">Register Browser for Approval</button><button id="verify-device-button">Verify Approved Device</button>
      <script id="device-verification-script" src="/static/patients/device_verification.js"
      data-register-options-url="create-options" data-register-verify-url="create-verify"
      data-authenticate-options-url="get-options" data-authenticate-verify-url="get-verify"></script>
      </body></html>` });
    await route.fulfill({ json: payload });
  });
  const harnessUrl = new URL("/__synthetic_webauthn_review__/", page.url());
  harnessUrl.hostname = "localhost"; // WebAuthn RP IDs cannot be IP addresses.
  await page.goto(harnessUrl.href);
  await page.getByRole("button", { name: "Register Browser for Approval" }).click();
  await expect(page.getByRole("status")).toHaveText("Synthetic registration captured");
  expect(registration.id).toBe(registration.rawId);
  expect(registration.type).toBe("public-key");
  expect(Buffer.from(registration.response.attestationObject, "base64url").length).toBeGreaterThan(30);
  expect(JSON.parse(Buffer.from(registration.response.clientDataJSON, "base64url")).type).toBe("webauthn.create");
  await page.getByRole("button", { name: "Verify Approved Device" }).click();
  await expect(page.getByRole("status")).toHaveText("Synthetic assertion captured");
  expect(assertion.rawId).toBe(registration.rawId);
  expect(Buffer.from(assertion.response.authenticatorData, "base64url").length).toBeGreaterThanOrEqual(37);
  expect(Buffer.from(assertion.response.signature, "base64url").length).toBeGreaterThan(30);
  expect(JSON.parse(Buffer.from(assertion.response.clientDataJSON, "base64url")).type).toBe("webauthn.get");
  await cdp.detach();
});
