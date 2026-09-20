(() => {
  const PREVIEW_EVENT = "case-edit-preview-refresh";
  const IDENTITY_EVENT = "case-edit-identity-refresh";
  const PREVIEW_FIELDS = new Set([
    "category",
    "subcategory",
    "status",
    "uhid",
    "first_name",
    "last_name",
    "gender",
    "blood_group",
    "date_of_birth",
    "age",
    "place",
    "phone_number",
    "alternate_phone_number",
    "diagnosis",
    "referred_by",
    "notes",
    "rch_number",
    "rch_bypass",
    "lmp",
    "edd",
    "usg_edd",
    "surgical_pathway",
    "surgery_done",
    "surgery_date",
    "review_frequency",
    "review_date",
    "high_risk",
    "gravida",
    "para",
    "abortions",
    "living",
    "ftnd",
    "lscs",
    "ncd_flags",
    "anc_high_risk_reasons",
  ]);
  const PREVIEW_INPUT_FIELDS = new Set([
    "uhid",
    "first_name",
    "last_name",
    "age",
    "place",
    "phone_number",
    "alternate_phone_number",
    "diagnosis",
    "referred_by",
    "notes",
  ]);
  const IDENTITY_FIELDS = new Set(["uhid", "phone_number", "alternate_phone_number"]);
  const HELP_STORAGE_KEY = "medtrack.caseEdit.helpVisible";
  const PRESERVED_FIELD_NAMES = new Set([
    "subcategory",
    "rch_number",
    "rch_bypass",
    "lmp",
    "edd",
    "usg_edd",
    "gravida",
    "para",
    "abortions",
    "living",
    "ftnd",
    "lscs",
    "surgical_pathway",
    "surgery_done",
    "surgery_date",
    "review_frequency",
    "review_date",
    "high_risk",
    "ncd_flags",
    "anc_high_risk_reasons",
  ]);
  const GPLA_FIELDS = ["gravida", "para", "abortions", "living"];
  const DELIVERY_FIELDS = ["ftnd", "lscs"];
  const PRIMI_VALUES = [1, 0, 0, 0];
  let draftState;

  const debounce = (callback, waitMs) => {
    let timeoutId = null;
    return () => {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(callback, waitMs);
    };
  };

  const form = () => document.getElementById("case-edit-form");
  const workflowShell = () => document.getElementById("case-edit-shell");
  const workflowState = () => document.getElementById("case-edit-shell-state");
  const helpToggle = () => document.querySelector("[data-case-edit-help-toggle]");

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

  function rememberFieldValue() { draftState?.remember(); }

  function restoreDraftValues() { return draftState?.restore() || false; }

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

  const { clampGplaValue, parseGplaValue, gplaCounterElements, gplaInputs, deliveryInputs, deliverySection, deliveryHint, deliveryValidation, hasExplicitGplaValue, isPrimiSelection, syncGplaPrimiToggle, deliveryModeTotal, deliveryFieldMax, setDeliveryValidationState, applyDeliveryValues, syncDeliveryModeState, syncGplaCounter, updateGplaSummary, syncGplaCounters, applyGplaValues, calculateAgeFromDob, updateAgeBehavior, updateGplaWarning, validateDeliveryModeBeforeSubmit } = window.medtrackClinicalControls;

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
    document.querySelectorAll("[data-case-edit-submit-button]").forEach((button) => {
      button.disabled = isSubmitting;
      button.querySelector(".spinner-border")?.classList.toggle("d-none", !isSubmitting);
      const label = button.querySelector(".case-edit-submit-label");
      if (label) {
        label.textContent = isSubmitting ? "Saving..." : "Save Changes";
      }
    });
  }

  function bindDelegatedEvents() {
    const caseForm = form();
    if (!caseForm || caseForm.dataset.caseEditBound === "true") return;
    caseForm.dataset.caseEditBound = "true";

    const triggerPreview = debounce(() => {
      const previewSync = document.getElementById("case-edit-preview-sync");
      if (window.htmx && previewSync) {
        window.htmx.trigger(previewSync, PREVIEW_EVENT);
      }
    }, 220);
    const triggerIdentity = debounce(() => {
      const identitySync = document.getElementById("case-edit-identity-sync");
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

      if (
        PREVIEW_FIELDS.has(target.name)
        && (event.type === "change" || (event.type === "input" && PREVIEW_INPUT_FIELDS.has(target.name)))
      ) {
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
      if (GPLA_FIELDS.includes(target.name) || DELIVERY_FIELDS.includes(target.name)) {
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
      const maxValue = deliveryFieldMax(input);
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

      const deliveryValidationResult = validateDeliveryModeBeforeSubmit();
      if (deliveryValidationResult?.input) {
        event.preventDefault();
        attachClientError(deliveryValidationResult.input, deliveryValidationResult.message);
        deliveryValidationResult.input.scrollIntoView({ behavior: "smooth", block: "center" });
        focusField(deliveryValidationResult.input);
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

  function initAutocomplete(inputId, fieldName) {
    const caseForm = form();
    const autocompleteUrl = caseForm?.dataset.caseAutocompleteUrl;
    const inputEl = document.getElementById(inputId);
    if (!autocompleteUrl || !inputEl) return;

    const container = inputEl.closest(".case-create-field") || inputEl.parentElement;
    if (!container) return;
    container.classList.add("position-relative");

    const panelId = `${inputId}-autocomplete`;
    const panelEl = document.createElement("div");
    panelEl.id = panelId;
    panelEl.className = "autocomplete-panel list-group shadow-sm d-none";
    panelEl.setAttribute("role", "listbox");
    panelEl.setAttribute("aria-label", `${fieldName} suggestions`);
    container.appendChild(panelEl);
    inputEl.setAttribute("autocomplete", "off");
    inputEl.setAttribute("aria-controls", panelId);

    let suggestions = [];
    let activeIndex = -1;
    let currentRequestId = 0;
    let controller = null;
    let debounceHandle = null;

    function closePanel() {
      currentRequestId += 1;
      controller?.abort();
      controller = null;
      window.clearTimeout(debounceHandle);
      panelEl.classList.add("d-none");
      panelEl.innerHTML = "";
      suggestions = [];
      activeIndex = -1;
      inputEl.removeAttribute("aria-activedescendant");
    }

    function selectSuggestion(index) {
      if (index < 0 || index >= suggestions.length) return;
      inputEl.value = suggestions[index];
      inputEl.dispatchEvent(new Event("change", { bubbles: true }));
      closePanel();
    }

    function setActiveSuggestion(index) {
      activeIndex = index;
      Array.from(panelEl.children).forEach((itemEl, itemIndex) => {
        itemEl.classList.toggle("active", itemIndex === activeIndex);
      });
      if (activeIndex >= 0) {
        const activeEl = panelEl.children[activeIndex];
        if (activeEl) {
          inputEl.setAttribute("aria-activedescendant", activeEl.id);
          activeEl.scrollIntoView({ block: "nearest" });
        }
      } else {
        inputEl.removeAttribute("aria-activedescendant");
      }
    }

    function renderSuggestions(items) {
      panelEl.innerHTML = "";
      suggestions = items;
      activeIndex = -1;

      if (!items.length) {
        closePanel();
        return;
      }

      items.forEach((item, index) => {
        const itemEl = document.createElement("button");
        itemEl.type = "button";
        itemEl.className = "list-group-item list-group-item-action py-1 px-2 small";
        itemEl.id = `${panelId}-item-${index}`;
        itemEl.setAttribute("role", "option");
        itemEl.textContent = item;
        itemEl.addEventListener("mouseenter", () => setActiveSuggestion(index));
        itemEl.addEventListener("mousedown", (event) => {
          event.preventDefault();
          selectSuggestion(index);
        });
        panelEl.appendChild(itemEl);
      });

      panelEl.classList.remove("d-none");
    }

    async function fetchSuggestions(query) {
      const requestId = ++currentRequestId;
      controller?.abort();
      controller = new AbortController();
      const params = new URLSearchParams({ field: fieldName, q: query });
      try {
        const response = await fetch(`${autocompleteUrl}?${params.toString()}`, {
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (!response.ok || requestId !== currentRequestId) {
          return;
        }
        const data = await response.json();
        if (requestId !== currentRequestId || inputEl.value.trim() !== query || document.activeElement !== inputEl) return;
        renderSuggestions(Array.isArray(data) ? data : []);
      } catch {
        if (requestId === currentRequestId) closePanel();
      }
    }

    inputEl.addEventListener("input", () => {
      const query = inputEl.value.trim();
      closePanel();
      if (debounceHandle) {
        window.clearTimeout(debounceHandle);
      }
      if (query.length < 2) {
        closePanel();
        return;
      }
      debounceHandle = window.setTimeout(() => fetchSuggestions(query), 200);
    });

    inputEl.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closePanel();
        return;
      }
      if (panelEl.classList.contains("d-none")) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveSuggestion((activeIndex + 1) % suggestions.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveSuggestion((activeIndex - 1 + suggestions.length) % suggestions.length);
      } else if (event.key === "Enter") {
        if (activeIndex >= 0) {
          event.preventDefault();
          selectSuggestion(activeIndex);
        }
      }
    });

    inputEl.addEventListener("blur", () => {
      window.setTimeout(closePanel, 120);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    draftState = window.medtrackCaseFormState({ form: form(), previewId: "case-edit-preview-sync", identityId: "case-edit-identity-sync", fields: PRESERVED_FIELD_NAMES });
    syncHelpMode(readHelpPreference());
    bindHelpToggle();
    bindDelegatedEvents();
    syncWorkflowState();
    syncGenderBehavior();
    updateAgeBehavior();
    syncGplaCounters();
    updateGplaWarning();
    focusFirstServerError();
    initAutocomplete("id_place", "place");
    initAutocomplete("id_diagnosis", "diagnosis");
    initAutocomplete("id_referred_by", "referred_by");
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (!draftState?.completed(event)) return;
    const restored = restoreDraftValues();
    syncWorkflowState();
    syncGenderBehavior();
    updateAgeBehavior();
    syncGplaCounters();
    updateGplaWarning();
    if (restored) {
      syncGplaCounters();
      const previewSync = document.getElementById("case-edit-preview-sync");
      if (window.htmx && previewSync) {
        window.htmx.trigger(previewSync, PREVIEW_EVENT);
      }
    }
  });

  window.addEventListener("pageshow", () => {
    disableSubmitButtons(false);
  });
})();
