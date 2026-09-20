(() => {
  const SOURCE_SELECTOR = 'input[data-crayons-datepicker="true"]';
  const PICKER_FIELD_ATTR = "data-crayons-datepicker-for";
  let anonymousInputCount = 0;
  let runtimePromise;

  function ensureRuntime() {
    if (runtimePromise) return runtimePromise;
    const config = document.getElementById("medtrack-datepicker-script").dataset;
    const loadStyles = (href) => new Promise((resolve, reject) => {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.onload = resolve;
      link.onerror = reject;
      // Preserve the original vendor -> datepicker -> app cascade.
      document.head.insertBefore(link, document.getElementById("medtrack-base-styles"));
    });
    const loadScript = new Promise((resolve, reject) => {
      const moduleScript = document.createElement("script");
      moduleScript.type = "module";
      moduleScript.src = config.moduleUrl;
      const legacyScript = document.createElement("script");
      legacyScript.noModule = true;
      legacyScript.src = config.legacyUrl;
      const supportedScript = "noModule" in moduleScript ? moduleScript : legacyScript;
      supportedScript.onload = resolve;
      supportedScript.onerror = reject;
      document.body.append(moduleScript, legacyScript);
    });
    runtimePromise = Promise.all([
      loadStyles(config.vendorCssUrl), loadStyles(config.datepickerCssUrl), loadScript,
    ]).then(() => customElements.whenDefined("fw-datepicker"));
    return runtimePromise;
  }

  function escapeSelectorValue(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return String(value).replace(/([ #;?%&,.+*~':"!^$[\]()=>|/@])/g, "\\$1");
  }

  function findPickerForInput(input) {
    if (!input || !input.id) {
      return null;
    }
    return document.querySelector(`fw-datepicker[${PICKER_FIELD_ATTR}="${escapeSelectorValue(input.id)}"]`);
  }

  function ensureInputId(input) {
    if (!input) {
      return "";
    }
    if (input.id) {
      return input.id;
    }
    const baseId = `id_${input.name || "date_field"}`;
    let candidate = baseId;
    while (document.getElementById(candidate)) {
      anonymousInputCount += 1;
      candidate = `${baseId}_${anonymousInputCount}`;
    }
    input.id = candidate;
    return candidate;
  }

  function normalizeDateValue(value, displayFormat = "dd/MM/yyyy") {
    if (typeof value !== "string") {
      return "";
    }
    const trimmedValue = value.trim();
    if (!trimmedValue) {
      return "";
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmedValue)) {
      return trimmedValue;
    }
    const isoDateTimeMatch = trimmedValue.match(/^(\d{4}-\d{2}-\d{2})T/);
    if (isoDateTimeMatch) {
      return isoDateTimeMatch[1];
    }
    if (displayFormat === "dd/MM/yyyy") {
      const parts = trimmedValue.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (parts) {
        return `${parts[3]}-${parts[2]}-${parts[1]}`;
      }
    }
    return "";
  }

  function syncPickerState(picker, sourceInput) {
    if (!picker || !sourceInput) {
      return;
    }

    const showFooter = sourceInput.dataset.crayonsDatepickerShowFooter === "true";
    picker.showFooter = showFooter;

    if (sourceInput.required) {
      picker.setAttribute("required", "");
    } else {
      picker.removeAttribute("required");
    }

    picker.disabled = Boolean(sourceInput.disabled);
    if (sourceInput.disabled) {
      picker.setAttribute("disabled", "");
    } else {
      picker.removeAttribute("disabled");
    }

    picker.readonly = Boolean(sourceInput.readOnly);
    if (sourceInput.readOnly) {
      picker.setAttribute("readonly", "");
    } else {
      picker.removeAttribute("readonly");
    }

    if (sourceInput.min) {
      picker.setAttribute("min-date", sourceInput.min);
    } else {
      picker.removeAttribute("min-date");
    }

    if (sourceInput.max) {
      picker.setAttribute("max-date", sourceInput.max);
    } else {
      picker.removeAttribute("max-date");
    }
    void syncAccessibility(picker, sourceInput);
  }

  async function syncAccessibility(picker, sourceInput) {
    if (!picker.isConnected) return;
    await window.customElements?.whenDefined("fw-datepicker");
    await picker.componentOnReady?.();
    const root = picker.shadowRoot || picker;
    const field = root.querySelector("fw-input.date-input, fw-input.range-date-input");
    if (!field) return;
    await window.customElements?.whenDefined("fw-input");
    await field.componentOnReady?.();
    const nativeInput = (field.shadowRoot || field).querySelector("input");
    if (!nativeInput) return;
    const labels = Array.from(sourceInput.labels || document.querySelectorAll(`label[for="${escapeSelectorValue(sourceInput.id)}"]`));
    const name = sourceInput.getAttribute("aria-label")
      || labels.map((label) => label.textContent.replace(/\s*\*\s*$/, "").trim()).join(" ");
    if (name) nativeInput.setAttribute("aria-label", name);
    // IDs outside a shadow tree cannot describe the internal input. Copy only
    // their accessible description; retain the existing visible help/errors.
    const descriptions = (sourceInput.getAttribute("aria-describedby") || "").split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent.trim()).filter(Boolean);
    const wrapper = sourceInput.closest(".case-create-field, .mb-3, .form-group");
    wrapper?.querySelectorAll(".invalid-feedback").forEach((error) => descriptions.push(error.textContent.trim()));
    if (descriptions.length) nativeInput.setAttribute("aria-description", [...new Set(descriptions)].join(" "));
    else nativeInput.removeAttribute("aria-description");
    nativeInput.setAttribute("aria-invalid", String(picker.classList.contains("is-invalid") || sourceInput.getAttribute("aria-invalid") === "true"));
  }

  function observeSourceInput(picker, sourceInput) {
    if (!picker || !sourceInput || typeof MutationObserver !== "function") {
      return;
    }

    const observer = new MutationObserver(() => {
      syncPickerState(picker, sourceInput);
    });
    observer.observe(sourceInput, {
      attributes: true,
      attributeFilter: ["disabled", "readonly", "required", "min", "max"],
    });
  }

  function toggleInvalidState(input, isInvalid) {
    const picker = findPickerForInput(input);
    const target = picker || input;
    if (target) {
      target.classList.toggle("is-invalid", Boolean(isInvalid));
    }
    if (picker) void syncAccessibility(picker, input);
  }

  function focusInput(input) {
    const picker = findPickerForInput(input);
    if (picker) {
      void window.customElements.whenDefined("fw-datepicker").then(async () => {
        await picker.componentOnReady?.();
        await picker.setFocus?.();
      });
      return picker;
    }
    if (input && typeof input.focus === "function") {
      input.focus();
    }
    return input;
  }

  async function syncSourceValue(picker, sourceInput, { clearFirst = false } = {}) {
    if (!picker || !sourceInput) {
      return "";
    }
    if (clearFirst) {
      sourceInput.value = "";
    }

    const displayFormat = sourceInput.dataset.crayonsDatepickerFormat || "dd/MM/yyyy";
    let nextValue = sourceInput.value || "";
    try {
      const value =
        typeof picker.getValue === "function"
          ? await picker.getValue()
          : typeof picker.value === "string"
            ? picker.value
            : "";
      nextValue = normalizeDateValue(typeof value === "string" ? value : "", displayFormat);
    } catch (error) {
      nextValue = normalizeDateValue(typeof picker.value === "string" ? picker.value : "", displayFormat);
    }

    sourceInput.value = nextValue;
    sourceInput.dispatchEvent(new Event("input", { bubbles: true }));
    sourceInput.dispatchEvent(new Event("change", { bubbles: true }));
    toggleInvalidState(sourceInput, false);
    return sourceInput.value;
  }

  function enhanceInput(sourceInput) {
    if (!sourceInput || sourceInput.dataset.crayonsDatepickerReady === "true") {
      return;
    }

    ensureInputId(sourceInput);

    const displayFormat = sourceInput.dataset.crayonsDatepickerFormat || "dd/MM/yyyy";
    const normalizedInitialValue = normalizeDateValue(sourceInput.value || "", displayFormat);
    if (normalizedInitialValue) {
      sourceInput.value = normalizedInitialValue;
    }

    const picker = document.createElement("fw-datepicker");
    picker.className = "medtrack-crayons-picker";
    picker.setAttribute(PICKER_FIELD_ATTR, sourceInput.id);
    picker.setAttribute(
      "display-format",
      displayFormat,
    );
    picker.setAttribute(
      "locale",
      sourceInput.dataset.crayonsDatepickerLocale || "en-IN",
    );
    picker.setAttribute(
      "placeholder",
      sourceInput.dataset.crayonsDatepickerPlaceholder || "dd/mm/yyyy",
    );
    const showFooter = sourceInput.dataset.crayonsDatepickerShowFooter === "true";
    picker.showFooter = showFooter;
    if (window.customElements && typeof window.customElements.whenDefined === "function") {
      void window.customElements.whenDefined("fw-datepicker").then(() => {
        picker.showFooter = showFooter;
        syncPickerState(picker, sourceInput);
      });
    }
    picker.setAttribute("clear-input", "");
    if (normalizedInitialValue) {
      picker.setAttribute("value", normalizedInitialValue);
    }

    const wrapper = document.createElement("div");
    wrapper.className = "medtrack-datepicker";
    wrapper.dataset.crayonsDatepickerWrapper = sourceInput.id;
    sourceInput.insertAdjacentElement("afterend", wrapper);
    wrapper.appendChild(picker);

    document.querySelectorAll(`label[for="${escapeSelectorValue(sourceInput.id)}"]`).forEach((label) => {
      label.addEventListener("click", (event) => {
        event.preventDefault();
        focusInput(sourceInput);
      });
    });

    sourceInput.type = "hidden";
    sourceInput.dataset.crayonsDatepickerSource = "true";
    sourceInput.dataset.crayonsDatepickerReady = "true";
    syncPickerState(picker, sourceInput);
    observeSourceInput(picker, sourceInput);

    let syncTimer = null;
    const scheduleSync = (options = {}) => {
      window.clearTimeout(syncTimer);
      syncTimer = window.setTimeout(() => {
        void syncSourceValue(picker, sourceInput, options);
      }, 0);
    };

    picker.addEventListener("fwChange", () => scheduleSync());
    picker.addEventListener("fwBlur", () => scheduleSync());
    picker.addEventListener("fwDateInput", () => scheduleSync({ clearFirst: true }));
    picker.addEventListener("fwFocus", () => { void syncAccessibility(picker, sourceInput); });
    void syncAccessibility(picker, sourceInput);
  }

  function initDatepickers(root = document) {
    const inputs = Array.from(root.querySelectorAll(SOURCE_SELECTOR));
    if (root.matches?.(SOURCE_SELECTOR)) inputs.unshift(root);
    if (!inputs.length) return;
    void ensureRuntime().then(() => {
      inputs.filter((input) => input.isConnected).forEach(enhanceInput);
    }).catch(() => {
      // Keep the original, labelled native inputs usable if assets cannot load.
    });
  }

  function observeDatepickers() {
    if (!document.body || typeof MutationObserver !== "function") {
      return;
    }
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof Element)) {
            return;
          }
          if (typeof node.querySelectorAll === "function") {
            initDatepickers(node);
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.medtrackCrayonsDatepicker = {
    focusInput,
    findPickerForInput,
    initDatepickers,
    toggleInvalidState,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initDatepickers();
      observeDatepickers();
    });
  } else {
    initDatepickers();
    observeDatepickers();
  }
})();
