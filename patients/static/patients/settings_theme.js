(() => {
    const previewRoot = document.querySelector("[data-theme-preview-root]");
    const hexInputs = document.querySelectorAll(".theme-hex-input");
    const pickerInputs = document.querySelectorAll(".theme-color-picker");
    const contrastSummary = document.querySelector("[data-contrast-summary]");
    const saveButton = document.querySelector("[data-theme-save]");
    const pairPrefixes = [
      "buttons-primary",
      "buttons-success",
      "buttons-secondary",
      "buttons-warning",
      "buttons-danger",
      "buttons-light",
      "alerts-info",
      "alerts-success",
      "alerts-warning",
      "alerts-danger",
      "alerts-light",
      "dashboard-today",
      "dashboard-recent",
      "dashboard-upcoming",
      "dashboard-overdue",
      "case-status-active",
      "case-status-completed",
      "case-status-cancelled",
      "case-status-loss-to-follow-up",
      "task-status-scheduled",
      "task-status-awaiting-reports",
      "task-status-completed",
      "task-status-cancelled",
      "vitals-status-low",
      "vitals-status-normal",
      "vitals-status-high",
      "vitals-status-neutral",
      "vitals-status-na",
      "search-gender-female",
      "search-gender-male",
      "search-gender-other",
    ];
    const chartPrefixes = [
      "blood-pressure",
      "pulse-rate",
      "spo2",
      "weight",
      "hemoglobin",
    ];
    const textContrastRules = [
      ["shell__page_text", "shell__page_bg", 4.5],
      ["shell__surface_text", "shell__surface_bg", 4.5],
      ["shell__muted_text", "shell__page_bg", 4.5],
      ["shell__muted_text", "shell__surface_bg", 4.5],
      ["shell__link", "shell__page_bg", 4.5],
      ["shell__link", "shell__surface_bg", 4.5],
      ["shell__link_hover", "shell__page_bg", 4.5],
      ["shell__link_hover", "shell__surface_bg", 4.5],
      ["nav__text", "nav__bg", 4.5],
      ["nav__control_text", "nav__control_bg", 4.5],
      ["nav__control_text", "nav__control_hover_bg", 4.5],
      ["nav__text", "nav__control_hover_bg", 4.5],
      ["nav__logout_text", "nav__logout_bg", 4.5],
      ["shell__surface_bg", "case_header__bg", 4.5],
      ["search__dropdown_text", "search__dropdown_bg", 4.5],
      ["search__dropdown_text", "search__result_hover_bg", 4.5],
      ["search__tag_text", "search__tag_bg", 4.5],
      ["buttons__primary__text", "buttons__primary__bg", 4.5],
      ["buttons__success__text", "buttons__success__bg", 4.5],
      ["buttons__secondary__text", "buttons__secondary__bg", 4.5],
      ["buttons__warning__text", "buttons__warning__bg", 4.5],
      ["buttons__danger__text", "buttons__danger__bg", 4.5],
      ["buttons__light__text", "buttons__light__bg", 4.5],
      ["buttons__primary__outline_text", "shell__page_bg", 4.5],
      ["buttons__primary__outline_text", "shell__surface_bg", 4.5],
      ["buttons__success__outline_text", "shell__page_bg", 4.5],
      ["buttons__success__outline_text", "shell__surface_bg", 4.5],
      ["buttons__secondary__outline_text", "shell__page_bg", 4.5],
      ["buttons__secondary__outline_text", "shell__surface_bg", 4.5],
      ["buttons__warning__outline_text", "shell__page_bg", 4.5],
      ["buttons__warning__outline_text", "shell__surface_bg", 4.5],
      ["buttons__danger__outline_text", "shell__page_bg", 4.5],
      ["buttons__danger__outline_text", "shell__surface_bg", 4.5],
      ["buttons__light__outline_text", "shell__page_bg", 4.5],
      ["buttons__light__outline_text", "shell__surface_bg", 4.5],
      ["alerts__info__text", "alerts__info__bg", 4.5],
      ["alerts__success__text", "alerts__success__bg", 4.5],
      ["alerts__warning__text", "alerts__warning__bg", 4.5],
      ["alerts__danger__text", "alerts__danger__bg", 4.5],
      ["alerts__light__text", "alerts__light__bg", 4.5],
      ["dashboard__today__text", "dashboard__today__bg", 4.5],
      ["dashboard__recent__text", "dashboard__recent__bg", 4.5],
      ["dashboard__upcoming__text", "dashboard__upcoming__bg", 4.5],
      ["dashboard__overdue__text", "dashboard__overdue__bg", 4.5],
      ["case_status__active__text", "case_status__active__bg", 4.5],
      ["case_status__completed__text", "case_status__completed__bg", 4.5],
      ["case_status__cancelled__text", "case_status__cancelled__bg", 4.5],
      ["case_status__loss_to_follow_up__text", "case_status__loss_to_follow_up__bg", 4.5],
      ["task_status__scheduled__text", "task_status__scheduled__bg", 4.5],
      ["task_status__awaiting_reports__text", "task_status__awaiting_reports__bg", 4.5],
      ["task_status__completed__text", "task_status__completed__bg", 4.5],
      ["task_status__cancelled__text", "task_status__cancelled__bg", 4.5],
      ["vitals_status__low__text", "vitals_status__low__bg", 4.5],
      ["vitals_status__normal__text", "vitals_status__normal__bg", 4.5],
      ["vitals_status__high__text", "vitals_status__high__bg", 4.5],
      ["vitals_status__neutral__text", "vitals_status__neutral__bg", 4.5],
      ["vitals_status__na__text", "vitals_status__na__bg", 4.5],
      ["search__gender_female__text", "search__gender_female__bg", 4.5],
      ["search__gender_male__text", "search__gender_male__bg", 4.5],
      ["search__gender_other__text", "search__gender_other__bg", 4.5],
    ];
    const derivedTextSections = [
      "buttons__",
      "alerts__",
      "dashboard__",
      "case_status__",
      "task_status__",
      "vitals_status__",
      "search__gender_",
    ];
    const derivedTextContrastRules = textContrastRules
      .filter(([textName, backgroundName]) => (
        derivedTextSections.some((prefix) => textName.startsWith(prefix))
        && backgroundName === textName.replace(/__text$/, "__bg")
      ))
      .map(([textName, backgroundName]) => [textName, backgroundName, 0.10, 4.5]);
    const focusContrastRules = [
      ["shell__focus_indicator", "shell__page_bg", 3.0],
      ["shell__focus_indicator", "shell__surface_bg", 3.0],
      ["shell__focus_indicator", "nav__bg", 3.0],
    ];
    const mixedTextContrastRules = [
      ["shell__surface_bg", "case_header__bg", "shell__page_text", 0.12, 4.5],
    ];

    function normalizeHex(value) {
      const normalized = String(value || "").trim().toLowerCase();
      return /^#[0-9a-f]{6}$/.test(normalized) ? normalized : "";
    }

    function hexToRgb(hexColor) {
      return [1, 3, 5].map((start) => Number.parseInt(hexColor.slice(start, start + 2), 16));
    }

    function relativeLuminance(hexColor) {
      const channels = hexToRgb(hexColor).map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.04045
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2]);
    }

    function contrastRatio(firstColor, secondColor) {
      const first = relativeLuminance(firstColor);
      const second = relativeLuminance(secondColor);
      return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
    }

    function markContrastInvalid(input) {
      if (!input) return;
      input.dataset.contrastInvalid = "true";
      input.setAttribute("aria-invalid", "true");
    }

    function updateContrastSummary() {
      hexInputs.forEach((input) => {
        if (input.dataset.contrastInvalid === "true") {
          delete input.dataset.contrastInvalid;
          input.removeAttribute("aria-invalid");
        }
      });

      let issueCount = 0;
      [...textContrastRules, ...focusContrastRules].forEach(([textName, backgroundName, minimum]) => {
        const textInput = document.querySelector(`[name="${textName}"]`);
        const backgroundInput = document.querySelector(`[name="${backgroundName}"]`);
        const textColor = normalizeHex(textInput?.value);
        const backgroundColor = normalizeHex(backgroundInput?.value);
        if (textColor && backgroundColor && contrastRatio(textColor, backgroundColor) < minimum) {
          issueCount += 1;
          markContrastInvalid(textInput);
          markContrastInvalid(backgroundInput);
        }
      });

      derivedTextContrastRules.forEach(([textName, backgroundName, mixRatio, minimum]) => {
        const textInput = document.querySelector(`[name="${textName}"]`);
        const backgroundInput = document.querySelector(`[name="${backgroundName}"]`);
        const textColor = normalizeHex(textInput?.value);
        const backgroundColor = normalizeHex(backgroundInput?.value);
        const interactionBackground = textColor && backgroundColor
          ? contrastSafeHoverColor(backgroundColor, textColor, mixRatio)
          : "";
        if (interactionBackground && contrastRatio(textColor, interactionBackground) < minimum) {
          issueCount += 1;
          markContrastInvalid(textInput);
          markContrastInvalid(backgroundInput);
        }
      });

      mixedTextContrastRules.forEach(([
        textName,
        backgroundName,
        mixTargetName,
        mixRatio,
        minimum,
      ]) => {
        const textInput = document.querySelector(`[name="${textName}"]`);
        const backgroundInput = document.querySelector(`[name="${backgroundName}"]`);
        const mixTargetInput = document.querySelector(`[name="${mixTargetName}"]`);
        const textColor = normalizeHex(textInput?.value);
        const backgroundColor = normalizeHex(backgroundInput?.value);
        const mixTargetColor = normalizeHex(mixTargetInput?.value);
        const interactionBackground = textColor && backgroundColor && mixTargetColor
          ? mixColors(backgroundColor, mixTargetColor, mixRatio)
          : "";
        if (interactionBackground && contrastRatio(textColor, interactionBackground) < minimum) {
          issueCount += 1;
          markContrastInvalid(textInput);
          markContrastInvalid(backgroundInput);
          markContrastInvalid(mixTargetInput);
        }
      });

      document.querySelectorAll(".theme-category-row").forEach((row) => {
        const backgroundInput = row.querySelector('[data-category-role="bg"]');
        const textInput = row.querySelector('[data-category-role="text"]');
        const backgroundColor = normalizeHex(backgroundInput?.value);
        const textColor = normalizeHex(textInput?.value);
        const hoverBackground = textColor && backgroundColor
          ? contrastSafeHoverColor(backgroundColor, textColor, 0.10)
          : "";
        if (
          textColor
          && backgroundColor
          && (
            contrastRatio(textColor, backgroundColor) < 4.5
            || contrastRatio(textColor, hoverBackground) < 4.5
          )
        ) {
          issueCount += 1;
          markContrastInvalid(textInput);
          markContrastInvalid(backgroundInput);
        }
      });

      if (contrastSummary) {
        contrastSummary.className = `alert py-2 ${issueCount ? "alert-danger" : "alert-success"}`;
        contrastSummary.textContent = issueCount
          ? `Contrast check: ${issueCount} issue${issueCount === 1 ? "" : "s"}. Save is blocked.`
          : "Contrast check: Pass.";
      }
      if (saveButton) {
        saveButton.disabled = issueCount > 0;
      }
    }

    function rgbToHex(rgb) {
      return `#${rgb.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
    }

    function mixColors(baseColor, targetColor, ratio) {
      const base = hexToRgb(baseColor);
      const target = hexToRgb(targetColor);
      const mixed = base.map((channel, index) => Math.round(channel + ((target[index] - channel) * ratio)));
      return rgbToHex(mixed);
    }

    function contrastSafeHoverColor(backgroundColor, textColor, ratio) {
      const lighter = mixColors(backgroundColor, "#ffffff", ratio);
      const darker = mixColors(backgroundColor, "#000000", ratio);
      return contrastRatio(textColor, lighter) >= contrastRatio(textColor, darker) ? lighter : darker;
    }

    function rgbaString(hexColor, alpha) {
      const [red, green, blue] = hexToRgb(hexColor);
      return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
    }

    function canonicalCategoryKey(name) {
      const collapsed = String(name || "").toUpperCase().replace(/[^A-Z]/g, "");
      if (collapsed === "ANC") return "ANC";
      if (collapsed === "SURGERY") return "SURGERY";
      if (collapsed === "MEDICINE" || collapsed === "NONSURGICAL") return "MEDICINE";
      return String(name || "").toUpperCase();
    }

    function readVar(name) {
      return getComputedStyle(previewRoot).getPropertyValue(name).trim();
    }

    function setVar(name, value) {
      if (previewRoot) {
        previewRoot.style.setProperty(name, value);
      }
    }

    function applyDerivedThemeVars() {
      if (!previewRoot) {
        return;
      }

      const shadowColor = normalizeHex(readVar("--theme-shell-shadow-color"));
      const surfaceBg = normalizeHex(readVar("--theme-shell-surface-bg"));
      const surfaceText = normalizeHex(readVar("--theme-shell-surface-text"));
      const focusIndicator = normalizeHex(readVar("--theme-shell-focus-indicator"));
      const searchDropdownBg = normalizeHex(readVar("--theme-search-dropdown-bg"));
      const searchDropdownText = normalizeHex(readVar("--theme-search-dropdown-text"));
      const searchTagBg = normalizeHex(readVar("--theme-search-tag-bg"));
      const searchTagText = normalizeHex(readVar("--theme-search-tag-text"));

      if (shadowColor) {
        setVar("--theme-shell-shadow", rgbaString(shadowColor, 0.12));
      }
      if (surfaceBg && surfaceText) {
        setVar("--theme-shell-surface-hover-bg", mixColors(surfaceBg, surfaceText, 0.10));
      }
      if (focusIndicator) {
        setVar("--theme-shell-focus-shadow", rgbaString(focusIndicator, 0.25));
      }
      if (searchDropdownBg && searchDropdownText) {
        setVar("--theme-search-dropdown-border", mixColors(searchDropdownBg, searchDropdownText, 0.20));
      }
      if (searchTagBg && searchTagText) {
        setVar("--theme-search-tag-border", mixColors(searchTagBg, searchTagText, 0.20));
      }

      pairPrefixes.forEach((prefix) => {
        const bg = normalizeHex(readVar(`--theme-${prefix}-bg`));
        const text = normalizeHex(readVar(`--theme-${prefix}-text`));
        if (!bg || !text) {
          return;
        }
        setVar(`--theme-${prefix}-border`, mixColors(bg, text, 0.20));
        setVar(`--theme-${prefix}-hover-bg`, contrastSafeHoverColor(bg, text, 0.10));
        setVar(`--theme-${prefix}-focus-shadow`, rgbaString(bg, 0.25));
      });

      chartPrefixes.forEach((prefix) => {
        const lineColor = normalizeHex(readVar(`--theme-vitals-chart-${prefix}`));
        if (!lineColor) {
          return;
        }
        setVar(`--theme-vitals-chart-${prefix}-fill`, rgbaString(lineColor, 0.18));
      });
    }

    function updateCategoryPreview(previewId) {
      const previewEl = document.getElementById(previewId);
      if (!previewEl) {
        return;
      }
      const row = previewEl.closest(".theme-category-row");
      if (!row) {
        return;
      }
      const bgInput = row.querySelector('[data-category-role="bg"]');
      const textInput = row.querySelector('[data-category-role="text"]');
      const bgColor = normalizeHex(bgInput?.value);
      const textColor = normalizeHex(textInput?.value);
      if (!bgColor || !textColor) {
        return;
      }
      const borderColor = mixColors(bgColor, textColor, 0.20);
      const hoverBg = contrastSafeHoverColor(bgColor, textColor, 0.10);
      previewEl.style.setProperty("--theme-category-bg", bgColor);
      previewEl.style.setProperty("--theme-category-text", textColor);
      previewEl.style.setProperty("--theme-category-border", borderColor);
      previewEl.style.setProperty("--theme-category-hover-bg", hoverBg);

      const categoryKey = canonicalCategoryKey(row.dataset.categoryName);
      document.querySelectorAll(`[data-preview-category="${categoryKey}"], [data-preview-category-tag="${categoryKey}"]`).forEach((sample) => {
        sample.style.setProperty("--theme-category-bg", bgColor);
        sample.style.setProperty("--theme-category-text", textColor);
        sample.style.setProperty("--theme-category-border", borderColor);
        sample.style.setProperty("--theme-category-hover-bg", hoverBg);
        sample.style.backgroundColor = bgColor;
        sample.style.color = textColor;
        sample.style.borderColor = borderColor;
      });
    }

    hexInputs.forEach((input) => {
      const picker = document.querySelector(`.theme-color-picker[data-sync-target="${input.id}"]`);
      const initialColor = normalizeHex(input.value);
      if (picker && initialColor) {
        picker.value = initialColor;
      }

      input.addEventListener("input", () => {
        const normalized = normalizeHex(input.value);
        if (!normalized) {
          return;
        }
        input.value = normalized;
        if (picker) {
          picker.value = normalized;
        }
        const previewVar = input.dataset.previewVar;
        if (previewVar) {
          setVar(previewVar, normalized);
          applyDerivedThemeVars();
        }
        if (input.dataset.categoryPreview) {
          updateCategoryPreview(input.dataset.categoryPreview);
        }
        updateContrastSummary();
      });
    });

    pickerInputs.forEach((picker) => {
      const target = document.getElementById(picker.dataset.syncTarget);
      if (!target) {
        return;
      }
      picker.addEventListener("input", () => {
        target.value = picker.value.toLowerCase();
        target.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });

    applyDerivedThemeVars();
    document.querySelectorAll("[data-category-preview]").forEach((input) => {
      updateCategoryPreview(input.dataset.categoryPreview);
    });
    updateContrastSummary();
  })();
