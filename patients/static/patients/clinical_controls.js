(() => {
  const GPLA_FIELDS = ["gravida", "para", "abortions", "living"];
  const DELIVERY_FIELDS = ["ftnd", "lscs"];
  const PRIMI_VALUES = [1, 0, 0, 0];
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

  function deliveryInputs() {
    return DELIVERY_FIELDS.map((name) => document.getElementById(`id_${name}`)).filter((input) => input instanceof HTMLInputElement);
  }

  function deliverySection() {
    return document.getElementById("case-create-delivery-section");
  }

  function deliveryHint() {
    return document.getElementById("case-create-delivery-hint");
  }

  function deliveryValidation() {
    return document.getElementById("case-create-delivery-validation");
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

  function deliveryModeTotal() {
    return deliveryInputs().reduce((total, input) => total + parseGplaValue(input.value), 0);
  }

  function deliveryFieldMax(input) {
    const baseMax = Number.parseInt(input?.dataset.gplaMax || "10", 10);
    if (!(input instanceof HTMLInputElement) || !DELIVERY_FIELDS.includes(input.name)) {
      return baseMax;
    }
    const para = parseGplaValue(document.getElementById("id_para")?.value || "0");
    const otherFieldName = input.name === "ftnd" ? "lscs" : "ftnd";
    const otherValue = parseGplaValue(document.getElementById(`id_${otherFieldName}`)?.value || "0");
    return Math.min(baseMax, Math.max(para - otherValue, 0));
  }

  function setDeliveryValidationState(state, message = "") {
    const validation = deliveryValidation();
    if (!(validation instanceof HTMLElement)) return;
    validation.classList.remove("d-none", "is-warning", "is-success", "is-error");
    if (!state || !message) {
      validation.textContent = "";
      validation.classList.add("d-none");
      return;
    }
    validation.textContent = message;
    validation.classList.add(state === "success" ? "is-success" : state === "error" ? "is-error" : "is-warning");
  }

  function applyDeliveryValues(values) {
    deliveryInputs().forEach((input, index) => {
      const nextValue = clampGplaValue(values[index] ?? 0);
      input.value = String(nextValue);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function syncDeliveryModeState() {
    const para = parseGplaValue(document.getElementById("id_para")?.value || "0");
    const showDeliveryMode = para > 0 && !isPrimiSelection();
    const section = deliverySection();
    const hint = deliveryHint();
    const currentTotal = deliveryModeTotal();

    if (hint) {
      hint.textContent = `Must equal Para (${para})`;
    }
    if (section) {
      section.classList.toggle("d-none", !showDeliveryMode);
    }

    if (!showDeliveryMode) {
      if (currentTotal > 0) {
        applyDeliveryValues([0, 0]);
        return true;
      }
      setDeliveryValidationState();
      return false;
    }

    if (currentTotal > para) {
      applyDeliveryValues([0, 0]);
      return true;
    }

    if (currentTotal === para) {
      setDeliveryValidationState("success", "Delivery count matches Para");
    } else {
      setDeliveryValidationState("warning", `FTND + LSCS = ${currentTotal}, need ${para} total`);
    }
    return false;
  }

  function syncGplaCounter(counter) {
    const input = counter?.querySelector("[data-gpla-input]");
    const valueEl = counter?.querySelector("[data-gpla-value]");
    const decrementButton = counter?.querySelector("[data-gpla-step='decrement']");
    const incrementButton = counter?.querySelector("[data-gpla-step='increment']");
    if (!(input instanceof HTMLInputElement) || !(valueEl instanceof HTMLElement)) return;

    const minValue = Number.parseInt(input.dataset.gplaMin || "0", 10);
    const maxValue = Number.parseInt(input.dataset.gplaMax || "10", 10);
    const stepMaxValue = deliveryFieldMax(input);
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
      incrementButton.disabled = value >= stepMaxValue;
    }
  }

  function updateGplaSummary() {
    const summary = document.getElementById("case-create-gpla-summary");
    if (!summary) return;

    const values = gplaInputs().map((input) => parseGplaValue(input.value));
    let summaryText = `G${values[0]} P${values[1]} A${values[2]} L${values[3]}`;
    const para = values[1];
    if (para > 0 && !isPrimiSelection()) {
      const [ftnd, lscs] = deliveryInputs().map((input) => parseGplaValue(input.value));
      summaryText += ` | FTND ${ftnd} LSCS ${lscs}`;
    }
    summary.textContent = summaryText;
  }

  function syncGplaCounters() {
    gplaCounterElements().forEach((counter) => syncGplaCounter(counter));
    syncGplaPrimiToggle();
    if (syncDeliveryModeState()) {
      return;
    }
    gplaCounterElements().forEach((counter) => syncGplaCounter(counter));
    updateGplaSummary();
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
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dobValue);
    if (!match) return "";
    const [year, month, day] = match.slice(1).map(Number);
    const dob = new Date(year, month - 1, day);
    if (dob.getFullYear() !== year || dob.getMonth() !== month - 1 || dob.getDate() !== day) return "";
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

    if (dobEl.value) {
      ageEl.value = calculateAgeFromDob(dobEl.value);
      ageEl.setAttribute("readonly", "readonly");
    } else {
      ageEl.removeAttribute("readonly");
    }
  }

  function updateGplaWarning() {
    const para = Number.parseInt(document.getElementById("id_para")?.value || "0", 10);
    const living = Number.parseInt(document.getElementById("id_living")?.value || "0", 10);
    const warning = document.getElementById("case-create-gpla-warning");
    if (!warning) return;
    warning.classList.toggle("d-none", !(living > para));
  }

  function validateDeliveryModeBeforeSubmit() {
    const para = parseGplaValue(document.getElementById("id_para")?.value || "0");
    if (!para || isPrimiSelection()) {
      return null;
    }
    const total = deliveryModeTotal();
    if (total === para) {
      return null;
    }
    return {
      input: document.getElementById("id_ftnd") || document.getElementById("id_lscs"),
      message: "FTND + LSCS must equal Para before saving.",
    };
  }


  window.medtrackClinicalControls = { clampGplaValue, parseGplaValue, gplaCounterElements, gplaInputs, deliveryInputs, deliverySection, deliveryHint, deliveryValidation, hasExplicitGplaValue, isPrimiSelection, syncGplaPrimiToggle, deliveryModeTotal, deliveryFieldMax, setDeliveryValidationState, applyDeliveryValues, syncDeliveryModeState, syncGplaCounter, updateGplaSummary, syncGplaCounters, applyGplaValues, calculateAgeFromDob, updateAgeBehavior, updateGplaWarning, validateDeliveryModeBeforeSubmit };
})();
