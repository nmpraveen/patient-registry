(() => {
  const PREVIEW_EVENT = "case-preview-refresh";
  const IDENTITY_EVENT = "case-identity-refresh";
  const PREVIEW_FIELDS = new Set([
    "category",
    "subcategory",
    "rch_number",
    "rch_bypass",
    "lmp",
    "edd",
    "usg_edd",
    "surgical_pathway",
    "surgery_date",
    "review_frequency",
    "review_date",
    "high_risk",
  ]);
  const IDENTITY_FIELDS = new Set(["uhid", "phone_number", "alternate_phone_number"]);
  const HELP_STORAGE_KEY = "medtrack.caseCreate.helpVisible";
  const PRESERVED_FIELD_NAMES = new Set([
    "rch_number",
    "lmp",
    "edd",
    "usg_edd",
    "gravida",
    "para",
    "abortions",
    "living",
    "subcategory",
    "surgical_pathway",
    "surgery_done",
    "surgery_date",
    "review_frequency",
    "review_date",
    "high_risk",
    "anc_high_risk_reasons",
  ]);
  const GPLA_FIELDS = ["gravida", "para", "abortions", "living"];
  const PRIMI_VALUES = [1, 0, 0, 0];
  const draftValues = new Map();

  const debounce = (callback, waitMs) => {
    let timeoutId = null;
    return () => {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(callback, waitMs);
    };
  };

  const form = () => document.getElementById("case-create-form");
  const workflowShell = () => document.getElementById("case-create-shell");
  const workflowState = () => document.getElementById("case-create-shell-state");
  const helpToggle = () => document.querySelector("[data-case-help-toggle]");

  function readHelpPreference() {
    try {
      return window.localStorage.getItem(HELP_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  }

  function writeHelpPreference(isVisible) {
    try {
      window.localStorage.setItem(HELP_STORAGE_KEY, isVisible ? "true" : "false");
    } catch {
      // Ignore storage failures and keep the toggle session-local.
    }
  }

  function syncHelpMode(isVisible) {
    const shell = workflowShell();
    const button = helpToggle();
    if (!shell || !button) return;
    shell.classList.toggle("is-help-visible", isVisible);
    button.textContent = isVisible ? "Hide Help" : "Show Help";
    button.setAttribute("aria-pressed", isVisible ? "true" : "false");
  }

  function bindHelpToggle() {
    const button = helpToggle();
    if (!button || button.dataset.caseHelpBound === "true") return;
    button.dataset.caseHelpBound = "true";
    button.addEventListener("click", () => {
      const shell = workflowShell();
      const nextVisible = !shell?.classList.contains("is-help-visible");
      syncHelpMode(nextVisible);
      writeHelpPreference(nextVisible);
    });
  }

  function fieldElements(name) {
    const caseForm = form();
    if (!caseForm || !window.CSS?.escape) return [];
    return Array.from(caseForm.querySelectorAll(`[name="${window.CSS.escape(name)}"]`));
  }

  function snapshotFieldValue(input) {
    const elements = fieldElements(input.name);
    if (!elements.length) return null;

    if (elements.length > 1 && elements[0].type === "checkbox") {
      return elements.filter((element) => element.checked).map((element) => element.value);
    }

    if (input.type === "checkbox") {
      return input.checked;
    }

    return input.value || "";
  }

  function rememberFieldValue(input) {
    if (!input?.name || !PRESERVED_FIELD_NAMES.has(input.name)) return;
    draftValues.set(input.name, snapshotFieldValue(input));
  }

  function restoreDraftValues() {
    let restored = false;

    draftValues.forEach((value, name) => {
      const elements = fieldElements(name);
      if (!elements.length) return;

      if (elements.length > 1 && elements[0].type === "checkbox") {
        if (!Array.isArray(value) || elements.some((element) => element.checked)) return;
        elements.forEach((element) => {
          element.checked = value.includes(element.value);
        });
        restored = true;
        return;
      }

      const input = elements[0];
      if (input.type === "checkbox") {
        if (!input.checked && value === true) {
          input.checked = true;
          restored = true;
        }
        return;
      }

      if (!input.value && value) {
        input.value = value;
        restored = true;
      }
    });

    return restored;
  }

  function syncWorkflowState() {
    const shell = workflowShell();
    const state = workflowState();
    if (!shell || !state) return;
    shell.dataset.workflowKey = state.dataset.workflowKey || "";
  }

  function selectedWorkflowKey() {
    const selectedCategory = document.querySelector(".case-create-choice input[name='category']:checked");
    const selectedChoice = selectedCategory?.closest(".case-create-choice");
    return selectedChoice?.dataset.workflowKey || workflowState()?.dataset.workflowKey || workflowShell()?.dataset.workflowKey || "";
  }

  function syncGenderBehavior() {
    const genderWrapper = document.querySelector(".case-create-gender-field");
    const genderInput = document.getElementById("id_gender");
    if (!genderWrapper || !genderInput) return;

    const isAnc = selectedWorkflowKey() === "anc";
    genderWrapper.classList.toggle("case-create-field--hidden", isAnc);

    if (isAnc) {
      if (genderInput.value && genderInput.value !== "FEMALE") {
        genderInput.dataset.previousNonAncValue = genderInput.value;
      }
      genderInput.value = "FEMALE";
      return;
    }

    if (genderInput.dataset.previousNonAncValue && genderInput.value === "FEMALE") {
      genderInput.value = genderInput.dataset.previousNonAncValue;
    }
  }

  function clampGplaValue(value, minValue = 0, maxValue = 10) {
    return Math.min(Math.max(value, minValue), maxValue);
  }

  function parseGplaValue(rawValue) {
    const parsed = Number.parseInt(String(rawValue ?? "").trim(), 10);
    if (Number.isNaN(parsed)) return 0;
    return clampGplaValue(parsed);
  }

  function gplaCounterElements() {
    return Array.from(document.querySelectorAll("[data-gpla-counter]"));
  }

  function gplaInputs() {
    return GPLA_FIELDS.map((name) => document.getElementById(`id_${name}`)).filter((input) => input instanceof HTMLInputElement);
  }

  function hasExplicitGplaValue(input) {
    return String(input?.value || "").trim() !== "";
  }

  function isPrimiSelection() {
    const inputs = gplaInputs();
    if (inputs.length !== GPLA_FIELDS.length || inputs.some((input) => !hasExplicitGplaValue(input))) {
      return false;
    }
    return inputs.every((input, index) => parseGplaValue(input.value) === PRIMI_VALUES[index]);
  }

  function syncGplaPrimiToggle() {
    const toggle = document.querySelector("[data-gpla-primi-toggle]");
    if (!(toggle instanceof HTMLButtonElement)) return;
    const isActive = isPrimiSelection();
    toggle.classList.toggle("is-active", isActive);
    toggle.setAttribute("aria-pressed", isActive ? "true" : "false");
  }

  function syncGplaCounter(counter) {
    const input = counter?.querySelector("[data-gpla-input]");
    const valueEl = counter?.querySelector("[data-gpla-value]");
    const decrementButton = counter?.querySelector("[data-gpla-step='decrement']");
    const incrementButton = counter?.querySelector("[data-gpla-step='increment']");
    if (!(input instanceof HTMLInputElement) || !(valueEl instanceof HTMLElement)) return;

    const minValue = Number.parseInt(input.dataset.gplaMin || "0", 10);
    const maxValue = Number.parseInt(input.dataset.gplaMax || "10", 10);
    const hasExplicitValue = String(input.value || "").trim() !== "";
    const value = clampGplaValue(parseGplaValue(input.value), minValue, maxValue);

    if (hasExplicitValue && String(value) !== input.value) {
      input.value = String(value);
    }

    valueEl.textContent = String(value);
    if (decrementButton instanceof HTMLButtonElement) {
      decrementButton.disabled = value <= minValue;
    }
    if (incrementButton instanceof HTMLButtonElement) {
      incrementButton.disabled = value >= maxValue;
    }
  }

  function updateGplaSummary() {
    const summary = document.getElementById("case-create-gpla-summary");
    if (!summary) return;

    const values = gplaInputs().map((input) => parseGplaValue(input.value));
    summary.textContent = `G${values[0]} P${values[1]} A${values[2]} L${values[3]}`;
  }

  function syncGplaCounters() {
    gplaCounterElements().forEach((counter) => syncGplaCounter(counter));
    updateGplaSummary();
    syncGplaPrimiToggle();
  }

  function applyGplaValues(values) {
    gplaInputs().forEach((input, index) => {
      const nextValue = clampGplaValue(values[index] ?? 0);
      input.value = String(nextValue);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function calculateAgeFromDob(dobValue) {
    if (!dobValue) return "";
    const dob = new Date(dobValue);
    if (Number.isNaN(dob.getTime())) return "";
    const today = new Date();
    let years = today.getFullYear() - dob.getFullYear();
    const monthDiff = today.getMonth() - dob.getMonth();
    const dayDiff = today.getDate() - dob.getDate();
    if (monthDiff < 0 || (monthDiff === 0 && dayDiff < 0)) {
      years -= 1;
    }
    return years >= 0 ? years : "";
  }

  function updateAgeBehavior() {
    const dobEl = document.getElementById("id_date_of_birth");
    const ageEl = document.getElementById("id_age");
    if (!dobEl || !ageEl) return;

    const helpText = ageEl.closest(".case-create-field")?.querySelector(".form-text");
    if (dobEl.value) {
      ageEl.value = calculateAgeFromDob(dobEl.value);
      ageEl.setAttribute("readonly", "readonly");
      if (helpText) {
        helpText.textContent = "Age is auto-calculated from DOB.";
      }
    } else {
      ageEl.removeAttribute("readonly");
      if (helpText) {
        helpText.textContent = "Enter age manually only if DOB is unknown.";
      }
    }
  }

  function updateGplaWarning() {
    const para = Number.parseInt(document.getElementById("id_para")?.value || "0", 10);
    const living = Number.parseInt(document.getElementById("id_living")?.value || "0", 10);
    const warning = document.getElementById("case-create-gpla-warning");
    if (!warning) return;
    warning.classList.toggle("d-none", !(living > para));
  }

  function clearClientErrors() {
    const caseForm = form();
    if (!caseForm) return;
    caseForm.querySelectorAll(".invalid-feedback[data-client-error='true']").forEach((node) => node.remove());
    caseForm.querySelectorAll(".is-client-invalid").forEach((node) => {
      node.classList.remove("is-client-invalid", "is-invalid");
    });
    caseForm.querySelectorAll("input.is-invalid, select.is-invalid, textarea.is-invalid").forEach((node) => {
      node.classList.remove("is-invalid");
    });
  }

  function attachClientError(input, message) {
    const wrapper = input.closest(".case-create-field, .case-create-grid");
    if (!wrapper) return;

    wrapper.classList.add("is-invalid", "is-client-invalid");
    if (window.medtrackCrayonsDatepicker?.toggleInvalidState) {
      window.medtrackCrayonsDatepicker.toggleInvalidState(input, true);
    } else {
      input.classList.add("is-invalid");
    }

    const feedback = document.createElement("div");
    feedback.className = "invalid-feedback d-block";
    feedback.dataset.clientError = "true";
    feedback.textContent = message;
    wrapper.appendChild(feedback);
  }

  function focusField(input) {
    if (!input) return;
    if (input instanceof HTMLInputElement && input.type === "hidden") {
      const gplaButton = input.closest("[data-gpla-counter]")?.querySelector("[data-gpla-step='increment']");
      if (gplaButton instanceof HTMLElement) {
        gplaButton.focus();
        return;
      }
    }
    if (window.medtrackCrayonsDatepicker?.focusInput) {
      const focused = window.medtrackCrayonsDatepicker.focusInput(input);
      if (focused) return;
    }
    input.focus();
  }

  function disableSubmitButtons(isSubmitting) {
    document.querySelectorAll("[data-case-submit-button]").forEach((button) => {
      button.disabled = isSubmitting;
      button.querySelector(".spinner-border")?.classList.toggle("d-none", !isSubmitting);
      const label = button.querySelector(".case-create-submit-label");
      if (label) {
        label.textContent = isSubmitting ? "Saving..." : "Save Case";
      }
    });
  }

  function bindDelegatedEvents() {
    const caseForm = form();
    if (!caseForm || caseForm.dataset.caseCreateBound === "true") return;
    caseForm.dataset.caseCreateBound = "true";

    const triggerPreview = debounce(() => {
      const previewSync = document.getElementById("case-create-preview-sync");
      if (window.htmx && previewSync) {
        window.htmx.trigger(previewSync, PREVIEW_EVENT);
      }
    }, 220);
    const triggerIdentity = debounce(() => {
      const identitySync = document.getElementById("case-create-identity-sync");
      if (window.htmx && identitySync) {
        window.htmx.trigger(identitySync, IDENTITY_EVENT);
      }
    }, 280);

    const maybeRefresh = (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement)) {
        return;
      }
      rememberFieldValue(target);

      if (PREVIEW_FIELDS.has(target.name) && event.type === "change") {
        triggerPreview();
      }
      if (IDENTITY_FIELDS.has(target.name)) {
        triggerIdentity();
      }
      if (target.name === "date_of_birth") {
        updateAgeBehavior();
      }
      if (target.name === "category") {
        syncGenderBehavior();
      }
      if (GPLA_FIELDS.includes(target.name)) {
        syncGplaCounters();
      }
      if (target.name === "para" || target.name === "living") {
        updateGplaWarning();
      }
    };

    caseForm.addEventListener("input", maybeRefresh, true);
    caseForm.addEventListener("change", maybeRefresh, true);
    caseForm.addEventListener("click", (event) => {
      const primiToggle = event.target.closest("[data-gpla-primi-toggle]");
      if (primiToggle instanceof HTMLButtonElement) {
        const nextValues = isPrimiSelection() ? [0, 0, 0, 0] : PRIMI_VALUES;
        applyGplaValues(nextValues);
        return;
      }

      const stepButton = event.target.closest("[data-gpla-step]");
      if (!(stepButton instanceof HTMLButtonElement)) return;

      const counter = stepButton.closest("[data-gpla-counter]");
      const input = counter?.querySelector("[data-gpla-input]");
      if (!(counter instanceof HTMLElement) || !(input instanceof HTMLInputElement)) return;

      const minValue = Number.parseInt(input.dataset.gplaMin || "0", 10);
      const maxValue = Number.parseInt(input.dataset.gplaMax || "10", 10);
      const delta = stepButton.dataset.gplaStep === "increment" ? 1 : -1;
      const nextValue = clampGplaValue(parseGplaValue(input.value) + delta, minValue, maxValue);

      input.value = String(nextValue);
      syncGplaCounter(counter);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    caseForm.addEventListener("submit", (event) => {
      clearClientErrors();
      let firstInvalid = null;
      const processedRadioNames = new Set();

      caseForm.querySelectorAll("input, select, textarea").forEach((input) => {
        if (input.disabled) return;
        if (input.type === "hidden" && input.dataset.crayonsDatepickerSource !== "true") return;
        if (!input.required) return;

        if (input.type === "radio") {
          if (processedRadioNames.has(input.name)) return;
          processedRadioNames.add(input.name);
          const radioGroup = fieldElements(input.name);
          if (!radioGroup.some((element) => element.checked)) {
            attachClientError(input, "This field is required.");
            if (!firstInvalid) {
              firstInvalid = input;
            }
          }
          return;
        }

        const value = (input.value || "").trim();
        const hasValue = input.type === "checkbox" ? input.checked : Boolean(value);
        if (!hasValue) {
          attachClientError(input, "This field is required.");
          if (!firstInvalid) {
            firstInvalid = input;
          }
        }
      });

      if (!caseForm.checkValidity() || firstInvalid) {
        event.preventDefault();
        const invalidTarget = firstInvalid || caseForm.querySelector(":invalid");
        if (invalidTarget) {
          invalidTarget.scrollIntoView({ behavior: "smooth", block: "center" });
          focusField(invalidTarget);
        }
        return;
      }

      disableSubmitButtons(true);
    });
  }

  function focusFirstServerError() {
    const invalidContainer = document.querySelector(".case-create-field.is-invalid, .case-create-grid.is-invalid");
    if (!invalidContainer) return;
    const invalidInput = invalidContainer.querySelector("input, select, textarea");
    if (!invalidInput) return;
    invalidContainer.scrollIntoView({ behavior: "smooth", block: "center" });
    focusField(invalidInput);
  }

  document.addEventListener("DOMContentLoaded", () => {
    syncHelpMode(readHelpPreference());
    bindHelpToggle();
    bindDelegatedEvents();
    syncWorkflowState();
    syncGenderBehavior();
    updateAgeBehavior();
    syncGplaCounters();
    updateGplaWarning();
    focusFirstServerError();
  });

  document.body.addEventListener("htmx:afterSwap", () => {
    syncWorkflowState();
    syncGenderBehavior();
    updateAgeBehavior();
    syncGplaCounters();
    updateGplaWarning();
    if (restoreDraftValues()) {
      syncGplaCounters();
      const previewSync = document.getElementById("case-create-preview-sync");
      if (window.htmx && previewSync) {
        window.htmx.trigger(previewSync, PREVIEW_EVENT);
      }
    }
  });

  window.addEventListener("pageshow", () => {
    disableSubmitButtons(false);
  });
})();
