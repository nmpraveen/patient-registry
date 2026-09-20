const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const source = (name) => fs.readFileSync(path.join(root, "patients/static/patients", name), "utf8");

test("DOB age compares calendar dates in a timezone behind UTC", () => {
  const previousTimezone = process.env.TZ;
  process.env.TZ = "America/New_York";
  try {
    class FixedDate extends Date {
      constructor(...args) { super(...(args.length ? args : ["2026-09-20T16:00:00-04:00"])); }
    }
    const ctx = { window: {}, Date: FixedDate };
    vm.createContext(ctx);
    vm.runInContext(source("clinical_controls.js"), ctx);
    const calculate = ctx.window.medtrackClinicalControls.calculateAgeFromDob;
    assert.equal(calculate("1980-09-21"), 45);
    assert.equal(calculate("1980-09-20"), 46);
    assert.equal(calculate("2026-09-20"), 0);
    assert.equal(calculate("2026-09-21"), "");
    assert.equal(calculate("2026-02-30"), "");
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = previousTimezone;
  }
});

function draftHarness() {
  let category = "anc";
  let inputs = { gravida: [{ value: "1", type: "hidden" }], high_risk: [{ value: "on", type: "checkbox", checked: false }], rch_number: [{ value: "", type: "text" }] };
  const events = {};
  const timers = new Map();
  let timerId = 0;
  const preview = { id: "preview", getAttribute: () => "refresh" };
  const form = {
    querySelector: () => ({ value: category }),
    querySelectorAll: (selector) => inputs[selector.match(/name="([^"]+)"/)[1]] || [],
    addEventListener() {},
  };
  const ctx = {
    CSS: { escape: (value) => value },
    FormData: class {
      entries() {
        return [["category", category], ...Object.entries(inputs).flatMap(([name, rows]) => rows.filter((row) => row.type !== "checkbox" || row.checked).map((row) => [name, row.value]))];
      }
    },
    document: { body: { addEventListener: (name, callback) => { events[name] = callback; } }, getElementById: () => preview },
    window: {
      setTimeout: (callback) => { timers.set(++timerId, callback); return timerId; },
      clearTimeout: (id) => timers.delete(id),
      htmx: { trigger: () => {} },
    },
  };
  vm.createContext(ctx);
  vm.runInContext(source("case_form_state.js"), ctx);
  const state = ctx.window.medtrackCaseFormState({ form, previewId: "preview", identityId: "identity", fields: new Set(Object.keys(inputs)) });
  return {
    state,
    get inputs() { return inputs; },
    replace(categoryValue, nextInputs) { category = categoryValue; inputs = nextInputs; },
    request() {
      const event = { detail: { elt: preview, xhr: {}, successful: true }, prevented: false, preventDefault() { this.prevented = true; } };
      events["htmx:beforeRequest"](event);
      return event;
    },
    response: (event) => events["htmx:beforeOnLoad"](event),
  };
}

test("a preview captured before a newer clinical edit cannot reach OOB swapping", () => {
  const harness = draftHarness();
  const request = harness.request();
  harness.inputs.gravida[0].value = "2";
  harness.state.remember();
  harness.response(request);
  assert.equal(request.prevented, true);
  assert.equal(harness.state.completed(request), false);
  assert.equal(harness.inputs.gravida[0].value, "2");
  const fresh = harness.request();
  harness.response(fresh);
  assert.equal(fresh.prevented, false);
  assert.equal(harness.state.completed(fresh), true);
});

test("category drafts restore intentional clearing and unchecked values without mixing workflows", () => {
  const harness = draftHarness();
  harness.state.remember();
  harness.replace("medicine", { rch_number: [{ value: "medicine", type: "text" }] });
  assert.equal(harness.state.restore(), false);
  harness.replace("anc", {
    gravida: [{ value: "7", type: "hidden" }],
    high_risk: [{ value: "on", type: "checkbox", checked: true }],
    rch_number: [{ value: "old-server-value", type: "text" }],
  });
  assert.equal(harness.state.restore(), true);
  assert.equal(harness.inputs.gravida[0].value, "1");
  assert.equal(harness.inputs.high_risk[0].checked, false);
  assert.equal(harness.inputs.rch_number[0].value, "");
});

test("a response for a category abandoned while loading is discarded", () => {
  const harness = draftHarness();
  const request = harness.request();
  harness.replace("medicine", harness.inputs);
  harness.response(request);
  assert.equal(request.prevented, true);
});

test("WebAuthn fallback serializes registration and assertion prototype accessors", () => {
  const node = { dataset: {}, addEventListener() {}, disabled: false };
  const ctx = {
    document: { getElementById: () => node },
    window: { PublicKeyCredential: {} }, navigator: { credentials: {} },
    Uint8Array, ArrayBuffer, btoa: (value) => Buffer.from(value, "binary").toString("base64"),
  };
  vm.createContext(ctx);
  vm.runInContext(source("device_verification.js").replace("    const creationOptionsFromJSON =", "    globalThis.serializeCredential = credentialToJSON;\n    const creationOptionsFromJSON ="), ctx);
  class Credential {
    constructor(response) { this.testResponse = response; }
    get id() { return "synthetic-credential"; }
    get rawId() { return Uint8Array.from([1, 2]).buffer; }
    get type() { return "public-key"; }
    get response() { return this.testResponse; }
    getClientExtensionResults() { return { credProps: { rk: true } }; }
  }
  class Attestation {
    get clientDataJSON() { return Uint8Array.from([3]).buffer; }
    get attestationObject() { return Uint8Array.from([4]).buffer; }
  }
  class Assertion {
    get clientDataJSON() { return Uint8Array.from([3]).buffer; }
    get authenticatorData() { return Uint8Array.from([5]).buffer; }
    get signature() { return Uint8Array.from([6]).buffer; }
    get userHandle() { return null; }
  }
  const attestation = ctx.serializeCredential(new Credential(new Attestation()));
  assert.equal(attestation.id, "synthetic-credential");
  assert.equal(attestation.rawId, "AQI");
  assert.equal(attestation.response.clientDataJSON, "Aw");
  assert.equal(attestation.response.attestationObject, "BA");
  const assertion = ctx.serializeCredential(new Credential(new Assertion()));
  assert.equal(assertion.response.authenticatorData, "BQ");
  assert.equal(assertion.response.signature, "Bg");
  assert.equal(assertion.response.userHandle, null);
});
