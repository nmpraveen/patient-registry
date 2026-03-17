(() => {
  const SOURCE_SELECTOR = 'input[data-crayons-datepicker="true"]';
  const PICKER_FIELD_ATTR = "data-crayons-datepicker-for";

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

  function toggleInvalidState(input, isInvalid) {
    const picker = findPickerForInput(input);
    const target = picker || input;
    if (target) {
      target.classList.toggle("is-invalid", Boolean(isInvalid));
    }
  }

  function focusInput(input) {
    const picker = findPickerForInput(input);
    if (picker && typeof picker.focus === "function") {
      picker.focus();
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
    if (typeof picker.getValue !== "function") {
      return sourceInput.value || "";
    }
    try {
      const value = await picker.getValue();
      sourceInput.value = typeof value === "string" ? value : "";
    } catch (error) {
      sourceInput.value = "";
    }
    sourceInput.dispatchEvent(new Event("input", { bubbles: true }));
    sourceInput.dispatchEvent(new Event("change", { bubbles: true }));
    toggleInvalidState(sourceInput, false);
    return sourceInput.value;
  }

  function enhanceInput(sourceInput) {
    if (!sourceInput || sourceInput.dataset.crayonsDatepickerReady === "true") {
      return;
    }

    if (!sourceInput.id) {
      sourceInput.id = `id_${sourceInput.name || "date_field"}`;
    }

    const picker = document.createElement("fw-datepicker");
    picker.className = "medtrack-crayons-picker";
    picker.setAttribute(PICKER_FIELD_ATTR, sourceInput.id);
    picker.setAttribute(
      "display-format",
      sourceInput.dataset.crayonsDatepickerFormat || "dd/MM/yyyy",
    );
    picker.setAttribute(
      "locale",
      sourceInput.dataset.crayonsDatepickerLocale || "en-IN",
    );
    picker.setAttribute(
      "placeholder",
      sourceInput.dataset.crayonsDatepickerPlaceholder || "dd/mm/yyyy",
    );
    picker.setAttribute("clear-input", "");
    if (sourceInput.value) {
      picker.setAttribute("value", sourceInput.value);
    }
    if (sourceInput.required) {
      picker.setAttribute("required", "");
    }
    if (sourceInput.disabled) {
      picker.setAttribute("disabled", "");
    }
    if (sourceInput.readOnly) {
      picker.setAttribute("readonly", "");
    }
    if (sourceInput.min) {
      picker.setAttribute("min-date", sourceInput.min);
    }
    if (sourceInput.max) {
      picker.setAttribute("max-date", sourceInput.max);
    }

    const wrapper = document.createElement("div");
    wrapper.className = "medtrack-datepicker";
    wrapper.dataset.crayonsDatepickerWrapper = sourceInput.id;
    sourceInput.insertAdjacentElement("afterend", wrapper);
    wrapper.appendChild(picker);

    sourceInput.type = "hidden";
    sourceInput.dataset.crayonsDatepickerSource = "true";
    sourceInput.dataset.crayonsDatepickerReady = "true";

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
  }

  function initDatepickers(root = document) {
    root.querySelectorAll(SOURCE_SELECTOR).forEach(enhanceInput);
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
          if (node.matches(SOURCE_SELECTOR)) {
            enhanceInput(node);
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
