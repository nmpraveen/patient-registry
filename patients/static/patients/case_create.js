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
  const PATIENT_LOOKUP_MIN_LENGTH = 3;
  const PATIENT_LOOKUP_DEBOUNCE_MS = 220;
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
  const patientSearchState = {
    controller: null,
    requestId: 0,
    results: [],
  };

  const debounce = (callback, waitMs) => {
    let timeoutId = null;
    return (...args) => {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => callback(...args), waitMs);
    };
  };

  const form = () => document.getElementById("case-create-form");
  const workflowShell = () => document.getElementById("case-create-shell");
  const workflowState = () => document.getElementById("case-create-shell-state");
  const helpToggle = () => document.querySelector("[data-case-help-toggle]");
  const patientModeInputs = () => Array.from(document.querySelectorAll("input[name='patient_mode']"));
  const patientModeCards = () => Array.from(document.querySelectorAll("[data-patient-mode-switch] .case-create-source-card"));
  const existingPatientPanel = () => document.getElementById("case-existing-patient-panel");
  const patientSearchStage = () => document.querySelector("[data-patient-search-stage]");
  const newPatientFields = () => document.querySelector("[data-new-patient-fields]");
  const newPatientIdentityFields = () => document.querySelector("[data-patient-identity-fields]");
  const identityChecks = () => document.getElementById("case-create-identity-checks");
  const newPatientIdentityChecks = () => document.querySelector("[data-new-patient-identity-checks]");
  const patientSearchInput = () => document.querySelector("[data-patient-search-input]");
  const patientSearchClear = () => document.querySelector("[data-patient-search-clear]");
  const patientSearchStatus = () => document.querySelector("[data-patient-search-status]");
  const patientSearchResults = () => document.querySelector("[data-patient-search-results]");
  const patientSearchFooter = () => document.querySelector("[data-patient-search-footer]");
  const patientSearchViewAll = () => document.querySelector("[data-patient-search-view-all]");
  const selectedPatientShell = () => document.querySelector("[data-selected-patient-shell]");
  const selectedPatientInput = () => document.getElementById("id_selected_patient");
  const queuePatientSearch = debounce((query) => {
    void searchExistingPatients(query);
  }, PATIENT_LOOKUP_DEBOUNCE_MS);

  function selectedPatientMode() {
    const selected = patientModeInputs().find((input) => input.checked);
    return selected?.value || "new";
  }

  function selectedPatientId() {
    return (selectedPatientInput()?.value || "").trim();
  }

  function setContainerFieldsDisabled(container, isDisabled) {
    if (!(container instanceof HTMLElement)) {
      return;
    }
    container.querySelectorAll("input, select, textarea, button").forEach((field) => {
      if (!(field instanceof HTMLInputElement || field instanceof HTMLSelectElement || field instanceof HTMLTextAreaElement || field instanceof HTMLButtonElement)) {
        return;
      }
      if (field.dataset.disableWithPatientMode === "false") {
        return;
      }
      field.disabled = isDisabled;
    });
  }

  function isFieldHiddenByLayout(field) {
    if (!(field instanceof HTMLElement)) {
      return false;
    }
    return Boolean(field.closest("[hidden], .d-none"));
  }

  function searchPanelMessage(query = "") {
    if (query.length >= PATIENT_LOOKUP_MIN_LENGTH) {
      return "";
    }
    return "";
  }

  function syncPatientMode() {
    const mode = selectedPatientMode();
    const isExisting = mode === "existing";
    const existingPanel = existingPatientPanel();
    const newFields = newPatientFields();
    const identityPanel = identityChecks();
    const newIdentityPanel = newPatientIdentityChecks();
    if (existingPanel) {
      existingPanel.hidden = !isExisting;
    }
    if (newFields) {
      newFields.hidden = isExisting;
    }
    setContainerFieldsDisabled(newPatientIdentityFields(), isExisting);
    if (identityPanel) {
      identityPanel.hidden = isExisting;
    }
    if (newIdentityPanel) {
      newIdentityPanel.hidden = isExisting;
    }

    patientModeCards().forEach((card) => {
      const input = card.querySelector("input[name='patient_mode']");
      card.classList.toggle("is-selected", Boolean(input?.checked));
    });

    if (!isExisting) {
      clearSelectedPatient({ clearIdentity: false, keepStatus: false, focusInput: false });
      hidePatientSearchResults();
      updatePatientSearchFooter("");
      clearPatientSearchValidation();
      updatePatientSearchStatus(searchPanelMessage());
      return;
    }

    if (selectedPatientId()) {
      setPatientSearchStageVisible(false);
      hidePatientSearchResults();
      updatePatientSearchFooter("");
      updatePatientSearchStatus("");
      return;
    }

    setPatientSearchStageVisible(true);
    const input = patientSearchInput();
    if (input) {
      const query = input.value.trim();
      updatePatientSearchStatus(searchPanelMessage(query));
      togglePatientSearchClearButton(query);
      if (query.length >= PATIENT_LOOKUP_MIN_LENGTH) {
        queuePatientSearch(query);
      }
    }
  }

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
    const wrapper = input.closest(".case-create-field, .case-create-grid, .case-create-patient-search");
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

  function clearPatientSearchValidation() {
    const search = patientSearchInput();
    if (search) {
      search.classList.remove("is-invalid");
    }
    const wrapper = search?.closest(".case-create-patient-search");
    wrapper?.classList.remove("is-invalid", "is-client-invalid");
    wrapper?.querySelectorAll(".invalid-feedback[data-client-error='true']").forEach((node) => node.remove());
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

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function patientAgeLabel(patient) {
    const ageDisplay = patient?.age_display;
    if (ageDisplay !== undefined && ageDisplay !== null && ageDisplay !== "") {
      return `${ageDisplay}`;
    }
    if (patient?.age !== undefined && patient?.age !== null && patient?.age !== "") {
      return `${patient.age}`;
    }
    return "\u2014";
  }

  function patientResultMeta(patient) {
    const parts = [
      patient?.uhid || "",
      patient?.phone_number || "",
      patient?.place || "",
      patient?.date_of_birth_display ? `DOB ${patient.date_of_birth_display}` : "",
      patientAgeLabel(patient) !== "\u2014" ? `Age ${patientAgeLabel(patient)}` : "",
    ];
    return parts.filter(Boolean).map((part) => escapeHtml(part)).join(" &middot; ");
  }

  function renderPatientTags(patient) {
    const chips = [
      `<span class="case-create-inline-chip is-active">${escapeHtml(`${patient.active_case_count || 0} active case${patient.active_case_count === 1 ? "" : "s"}`)}</span>`,
      `<span class="case-create-inline-chip">${escapeHtml(`${patient.case_count || 0} total case${patient.case_count === 1 ? "" : "s"}`)}</span>`,
    ];

    const tags = Array.isArray(patient?.tags) ? patient.tags : [];
    tags.forEach((tag) => {
      const kind = typeof tag?.kind === "string" ? escapeHtml(tag.kind) : "";
      const value = typeof tag?.value === "string" ? escapeHtml(tag.value) : "";
      chips.push(
        `<span class="global-search-tag"${kind ? ` data-tag-kind="${kind}"` : ""}${value ? ` data-tag-value="${value}"` : ""}>${escapeHtml(tag?.label || "")}</span>`
      );
    });

    return chips.join("");
  }

  function renderPatientCases(cases, actionsClass = "case-create-patient-result__actions") {
    if (!Array.isArray(cases) || !cases.length) {
      return `
        <div class="case-create-note">
          <div class="small fw-semibold">No active cases yet.</div>
          <div class="small text-muted">You can still use this patient and create the next case from this intake flow.</div>
        </div>
      `;
    }

    return cases.map((patientCase) => `
      <article class="case-create-patient-result__case">
        <div>
          <div class="case-create-patient-result__case-name">${escapeHtml(patientCase.category_name || "Case")}</div>
          <div class="case-create-patient-result__case-meta">${escapeHtml(patientCase.status || "")} &middot; ${escapeHtml(patientCase.diagnosis || patientCase.category_name || "")}</div>
        </div>
        <div class="${actionsClass}">
          <a class="btn btn-sm btn-outline-secondary" href="${escapeHtml(patientCase.detail_url || "#")}">Open Case</a>
        </div>
      </article>
    `).join("");
  }

  function renderSelectedPatient(patient) {
    return `
      <div class="case-create-selected-patient__card">
        <div class="case-create-selected-patient__header">
          <div>
            <div class="case-create-selected-patient__eyebrow">Selected patient</div>
            <div class="case-create-selected-patient__title">${escapeHtml(patient.name || patient.uhid || "Patient")}</div>
            <div class="case-create-selected-patient__meta">${escapeHtml(patient.uhid || "")}</div>
          </div>
          <div class="case-create-selected-patient__actions">
            <button class="btn btn-sm btn-outline-secondary" type="button" data-clear-selected-patient>Change patient</button>
          </div>
        </div>
        <dl class="case-create-selected-patient__facts">
          <div>
            <dt>Name</dt>
            <dd>${escapeHtml(patient.name || patient.uhid || "-")}</dd>
          </div>
          <div>
            <dt>Sex</dt>
            <dd>${escapeHtml(patient.gender || "-")}</dd>
          </div>
          <div>
            <dt>DOB</dt>
            <dd>${escapeHtml(patient.date_of_birth_display || "-")}</dd>
          </div>
          <div>
            <dt>Age</dt>
            <dd>${escapeHtml(patientAgeLabel(patient))}</dd>
          </div>
          <div>
            <dt>Place</dt>
            <dd>${escapeHtml(patient.place || "-")}</dd>
          </div>
          <div>
            <dt>Phone</dt>
            <dd>${escapeHtml(patient.phone_number || "-")}</dd>
          </div>
        </dl>
      </div>
    `;
  }

  function renderPatientResult(patient) {
    const isSelected = String(patient?.id || "") === selectedPatientId();
    return `
      <article class="case-create-patient-result${isSelected ? " is-selected" : ""}" data-patient-result-id="${escapeHtml(patient.id)}">
        <div class="case-create-patient-result__main">
          <div class="case-create-patient-result__title-row">
            <div>
              <div class="case-create-patient-result__title">${escapeHtml(patient.name || patient.uhid || "Patient")}</div>
              <div class="case-create-patient-result__meta">${patientResultMeta(patient)}</div>
            </div>
          </div>
          <div class="case-create-patient-result__headline">${escapeHtml(patient.diagnosis || "No active issue summary")}</div>
          <div class="case-create-patient-result__tags global-search-tags">
            ${renderPatientTags(patient)}
          </div>
          <div class="case-create-patient-result__cases">
            ${renderPatientCases(patient.cases)}
          </div>
        </div>
        <div class="case-create-patient-result__actions">
          <button class="btn btn-primary" type="button" data-use-patient-id="${escapeHtml(patient.id)}">Use Patient</button>
          <a class="btn btn-outline-secondary" href="${escapeHtml(patient.detail_url || "#")}">Open Patient</a>
        </div>
      </article>
    `;
  }

  function renderPatientEmptyState(query) {
    return `
      <div class="case-create-empty-state">
        <div class="case-create-empty-state__icon" aria-hidden="true">?</div>
        <div>
          <div class="fw-semibold">No matching patients yet.</div>
          <div class="small text-muted">No existing patient matched "${escapeHtml(query)}". Try a longer name, UHID, phone number, place, or full DOB.</div>
        </div>
      </div>
    `;
  }

  function hidePatientSearchResults() {
    const results = patientSearchResults();
    if (!results) return;
    results.hidden = true;
    results.replaceChildren();
    patientSearchState.results = [];
  }

  function updatePatientSearchStatus(message) {
    const status = patientSearchStatus();
    if (!status) return;
    status.textContent = message || "";
    status.hidden = !message;
  }

  function togglePatientSearchClearButton(query) {
    const clearButton = patientSearchClear();
    if (!clearButton) return;
    clearButton.hidden = !query;
  }

  function buildPatientListUrl(query) {
    const panel = existingPatientPanel();
    const baseUrl = panel?.dataset.patientListUrl || "";
    if (!baseUrl) return "";
    const params = new URLSearchParams();
    if (query) {
      params.set("q", query);
    }
    return params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl;
  }

  function updatePatientSearchFooter(query) {
    const footer = patientSearchFooter();
    const link = patientSearchViewAll();
    if (!footer || !link) return;

    if (query.length < PATIENT_LOOKUP_MIN_LENGTH) {
      footer.hidden = true;
      link.href = buildPatientListUrl("");
      return;
    }

    footer.hidden = false;
    link.href = buildPatientListUrl(query);
    link.textContent = "View all matching patients";
  }

  function setPatientFieldValue(fieldId, value) {
    const input = document.getElementById(fieldId);
    if (!input) return;
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else {
      input.value = value ?? "";
    }
  }

  function populatePatientIdentityFields(patient) {
    setPatientFieldValue("id_uhid", patient?.uhid || "");
    setPatientFieldValue("id_prefix", patient?.prefix || "");
    setPatientFieldValue("id_first_name", patient?.first_name || "");
    setPatientFieldValue("id_last_name", patient?.last_name || "");
    setPatientFieldValue("id_gender", patient?.gender || "");
    setPatientFieldValue("id_date_of_birth", patient?.date_of_birth || "");
    setPatientFieldValue("id_age", patient?.age ?? "");
    setPatientFieldValue("id_place", patient?.place || "");
    setPatientFieldValue("id_phone_number", patient?.phone_number || "");
    setPatientFieldValue("id_alternate_phone_number", patient?.alternate_phone_number || "");
    setPatientFieldValue("id_use_temporary_uhid", Boolean(patient?.is_temporary_id));
    updateAgeBehavior();
  }

  function clearPatientIdentityFields() {
    populatePatientIdentityFields({
      uhid: "",
      prefix: "",
      first_name: "",
      last_name: "",
      gender: "",
      date_of_birth: "",
      age: "",
      place: "",
      phone_number: "",
      alternate_phone_number: "",
      is_temporary_id: false,
    });
  }

  function renderSelectedPatientShell(patient) {
    const shell = selectedPatientShell();
    if (!shell) return;
    if (!patient) {
      shell.classList.add("d-none");
      shell.replaceChildren();
      return;
    }
    shell.classList.remove("d-none");
    shell.innerHTML = renderSelectedPatient(patient);
  }

  function setPatientSearchStageVisible(isVisible) {
    const stage = patientSearchStage();
    if (!stage) return;
    stage.hidden = !isVisible;
  }

  function refreshPatientResultSelection() {
    document.querySelectorAll("[data-patient-result-id]").forEach((result) => {
      result.classList.toggle("is-selected", result.dataset.patientResultId === selectedPatientId());
    });
  }

  function setSelectedPatient(patient) {
    const hiddenInput = selectedPatientInput();
    if (hiddenInput) {
      hiddenInput.value = patient?.id ? String(patient.id) : "";
    }
    if (patient) {
      populatePatientIdentityFields(patient);
      if (patientSearchInput()) {
        patientSearchInput().value = "";
      }
      togglePatientSearchClearButton("");
      hidePatientSearchResults();
      updatePatientSearchFooter("");
      setPatientSearchStageVisible(false);
      renderSelectedPatientShell(patient);
      updatePatientSearchStatus("");
      clearPatientSearchValidation();
    }
    refreshPatientResultSelection();
  }

  function clearSelectedPatient(options = {}) {
    const { clearIdentity = true, keepStatus = true, focusInput = false } = options;
    const hiddenInput = selectedPatientInput();
    if (hiddenInput) {
      hiddenInput.value = "";
    }
    renderSelectedPatientShell(null);
    if (clearIdentity) {
      clearPatientIdentityFields();
    }
    setPatientSearchStageVisible(true);
    if (patientSearchInput()) {
      patientSearchInput().value = "";
    }
    togglePatientSearchClearButton("");
    hidePatientSearchResults();
    updatePatientSearchFooter("");
    refreshPatientResultSelection();
    if (keepStatus) {
      const query = patientSearchInput()?.value.trim() || "";
      updatePatientSearchStatus(searchPanelMessage(query));
    }
    if (focusInput) {
      patientSearchInput()?.focus();
    }
  }

  function patientSearchUrl(query) {
    const panel = existingPatientPanel();
    const baseUrl = panel?.dataset.patientSearchUrl || "";
    if (!baseUrl) return "";
    const params = new URLSearchParams();
    params.set("q", query);
    return `${baseUrl}?${params.toString()}`;
  }

  async function searchExistingPatients(rawQuery) {
    if (selectedPatientMode() !== "existing") {
      return;
    }

    const query = String(rawQuery || "").trim();
    togglePatientSearchClearButton(query);
    clearPatientSearchValidation();

    if (query.length < PATIENT_LOOKUP_MIN_LENGTH) {
      if (patientSearchState.controller) {
        patientSearchState.controller.abort();
        patientSearchState.controller = null;
      }
      hidePatientSearchResults();
      updatePatientSearchFooter("");
      updatePatientSearchStatus(searchPanelMessage(query));
      return;
    }

    const url = patientSearchUrl(query);
    if (!url) return;

    patientSearchState.requestId += 1;
    const requestId = patientSearchState.requestId;
    if (patientSearchState.controller) {
      patientSearchState.controller.abort();
    }
    patientSearchState.controller = new AbortController();
    updatePatientSearchStatus("");

    try {
      const response = await fetch(url, {
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        signal: patientSearchState.controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Search request failed with ${response.status}`);
      }
      const payload = await response.json();
      if (requestId !== patientSearchState.requestId) {
        return;
      }

      patientSearchState.results = Array.isArray(payload?.results) ? payload.results : [];
      const results = patientSearchResults();
      if (!results) return;

      results.hidden = false;
      if (!patientSearchState.results.length) {
        results.innerHTML = renderPatientEmptyState(query);
        updatePatientSearchStatus("");
      } else {
        results.innerHTML = patientSearchState.results.map((patient) => renderPatientResult(patient)).join("");
        updatePatientSearchStatus("");
      }
      updatePatientSearchFooter(query);
      refreshPatientResultSelection();
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      hidePatientSearchResults();
      updatePatientSearchFooter(query);
      updatePatientSearchStatus("");
    }
  }

  function bindPatientSearch() {
    const input = patientSearchInput();
    if (!input || input.dataset.patientSearchBound === "true") {
      return;
    }

    input.dataset.patientSearchBound = "true";
    input.addEventListener("input", (event) => {
      const query = event.target.value.trim();
      togglePatientSearchClearButton(query);
      queuePatientSearch(query);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        input.value = "";
        togglePatientSearchClearButton("");
        hidePatientSearchResults();
        updatePatientSearchFooter("");
        updatePatientSearchStatus(searchPanelMessage());
        return;
      }
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      void searchExistingPatients(input.value.trim());
    });

    const clearButton = patientSearchClear();
    if (clearButton) {
      clearButton.addEventListener("click", () => {
        input.value = "";
        togglePatientSearchClearButton("");
        hidePatientSearchResults();
        updatePatientSearchFooter("");
        updatePatientSearchStatus(searchPanelMessage());
        clearPatientSearchValidation();
        input.focus();
      });
    }
  }

  function bindSubmitButtons() {
    if (document.body.dataset.caseCreateSubmitBound === "true") {
      return;
    }
    document.body.dataset.caseCreateSubmitBound = "true";
    document.body.addEventListener("click", (event) => {
      const submitButton = event.target.closest("[data-case-submit-button]");
      if (!(submitButton instanceof HTMLButtonElement) || submitButton.disabled) {
        return;
      }
      const caseForm = form();
      if (!(caseForm instanceof HTMLFormElement)) {
        return;
      }
      event.preventDefault();
      if (!validateCaseFormBeforeSubmit(caseForm)) {
        return;
      }
      disableSubmitButtons(true);
      HTMLFormElement.prototype.submit.call(caseForm);
    });
  }

  function validateCaseFormBeforeSubmit(caseForm) {
    clearClientErrors();
    clearPatientSearchValidation();

    if (selectedPatientMode() === "existing" && !selectedPatientId()) {
      const searchInput = patientSearchInput();
      if (searchInput) {
        attachClientError(searchInput, "Choose an existing patient before saving the case.");
        searchInput.scrollIntoView({ behavior: "smooth", block: "center" });
        focusField(searchInput);
      }
      return false;
    }

    let firstInvalid = null;
    const processedRadioNames = new Set();

    caseForm.querySelectorAll("input, select, textarea").forEach((input) => {
      if (input.disabled) return;
      if (input.type === "hidden" && input.dataset.crayonsDatepickerSource !== "true") return;
      if (isFieldHiddenByLayout(input) && input.dataset.crayonsDatepickerSource !== "true") return;
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
      const invalidTarget = firstInvalid || caseForm.querySelector(":invalid");
      if (invalidTarget) {
        invalidTarget.scrollIntoView({ behavior: "smooth", block: "center" });
        focusField(invalidTarget);
      }
      return false;
    }

    return true;
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
      if (target.name === "patient_mode") {
        syncPatientMode();
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
      const usePatientButton = event.target.closest("[data-use-patient-id]");
      if (usePatientButton instanceof HTMLButtonElement) {
        const patient = patientSearchState.results.find((result) => String(result.id) === usePatientButton.dataset.usePatientId);
        if (patient) {
          setSelectedPatient(patient);
        }
        return;
      }

      const clearSelectedPatientButton = event.target.closest("[data-clear-selected-patient]");
      if (clearSelectedPatientButton instanceof HTMLButtonElement) {
        clearSelectedPatient({ clearIdentity: true, keepStatus: true, focusInput: true });
        return;
      }

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
      if (!validateCaseFormBeforeSubmit(caseForm)) {
        event.preventDefault();
        return;
      }

      window.setTimeout(() => disableSubmitButtons(true), 0);
    });
  }

  function focusFirstServerError() {
    const invalidContainer = document.querySelector(".case-create-field.is-invalid, .case-create-grid.is-invalid, .case-create-patient-search.is-invalid");
    if (!invalidContainer) return;
    const invalidInput = invalidContainer.querySelector("input, select, textarea");
    if (!invalidInput) return;
    invalidContainer.scrollIntoView({ behavior: "smooth", block: "center" });
    focusField(invalidInput);
  }

  document.addEventListener("DOMContentLoaded", () => {
    syncHelpMode(readHelpPreference());
    bindHelpToggle();
    bindPatientSearch();
    bindSubmitButtons();
    bindDelegatedEvents();
    syncWorkflowState();
    syncPatientMode();
    syncGenderBehavior();
    updateAgeBehavior();
    syncGplaCounters();
    updateGplaWarning();
    togglePatientSearchClearButton(patientSearchInput()?.value.trim() || "");
    focusFirstServerError();
  });

  document.body.addEventListener("htmx:afterSwap", () => {
    syncWorkflowState();
    syncPatientMode();
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
