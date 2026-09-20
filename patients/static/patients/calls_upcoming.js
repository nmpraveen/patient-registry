(() => {
    const checkboxes = Array.from(document.querySelectorAll("[data-case-select]"));
    const form = document.querySelector(".calls-sheet-form");
    const selectedCountEl = document.querySelector("[data-selected-count]");
    const selectedPluralEl = document.querySelector("[data-selected-plural]");
    const applyButton = document.querySelector("[data-apply-button]");
    const outcomeSelect = document.getElementById("bulk-outcome");
    const bulkBar = document.querySelector("[data-calls-bulk-bar]");
    const bulkLinks = document.querySelector("[data-bulk-links]");
    const bulkControls = document.querySelector("[data-bulk-controls]");

    const updateSelectionState = () => {
      const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
      const hasSelection = selectedCount > 0;
      if (selectedCountEl) {
        selectedCountEl.textContent = String(selectedCount);
      }
      if (selectedPluralEl) {
        selectedPluralEl.textContent = selectedCount === 1 ? "" : "s";
      }
      if (bulkBar) {
        bulkBar.classList.toggle("is-active", hasSelection);
      }
      if (bulkLinks) {
        bulkLinks.hidden = !hasSelection;
      }
      if (bulkControls) {
        bulkControls.hidden = !hasSelection;
      }
      if (applyButton) {
        applyButton.disabled = selectedCount === 0 || !(outcomeSelect && outcomeSelect.value);
      }
    };

    document.querySelector("[data-select-visible]")?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        if (!checkbox.disabled) {
          checkbox.checked = true;
        }
      });
      updateSelectionState();
    });

    document.querySelector("[data-clear-selection]")?.addEventListener("click", () => {
      checkboxes.forEach((checkbox) => {
        checkbox.checked = false;
      });
      updateSelectionState();
    });

    checkboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", updateSelectionState);
      checkbox.addEventListener("click", (event) => event.stopPropagation());
    });
    outcomeSelect?.addEventListener("change", updateSelectionState);
    form?.addEventListener("submit", (event) => {
      const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length;
      const confirmed = selectedCount > 0 && window.confirm(
        `Apply this outcome to ${selectedCount} selected patient${selectedCount === 1 ? "" : "s"}?`,
      );
      if (!confirmed) {
        event.preventDefault();
      }
    });
    updateSelectionState();

    const listEl = document.querySelector("[data-calls-sheet-list]");
    const getCookie = (name) => {
      const cookieValue = document.cookie
        .split(";")
        .map((item) => item.trim())
        .find((item) => item.startsWith(`${name}=`));
      if (!cookieValue) {
        return "";
      }
      return decodeURIComponent(cookieValue.split("=").slice(1).join("="));
    };

    const getCallStatusDisplay = (status, failedAttemptCount) => {
      if (status === "CONFIRMED") {
        return { label: "Confirmed", tone: "success" };
      }
      if (status === "NOT_REACHABLE") {
        const count = Math.max(Number.parseInt(failedAttemptCount, 10) || 0, 0);
        return { label: count ? `Not reachable x${count}` : "Not reachable", tone: "danger" };
      }
      if (status === "INVALID_CONTACT") {
        return { label: "Invalid contact", tone: "neutral" };
      }
      if (status === "LOST") {
        return { label: "Lost follow-up", tone: "neutral" };
      }
      if (status === "CALL_BACK_LATER") {
        return { label: "Call back later", tone: "warning" };
      }
      return { label: "Not contacted", tone: "warning" };
    };

    const formatLatestCallCopy = (callLog) => {
      if (!callLog || !callLog.outcome_label) {
        return "Not contacted yet";
      }
      const segments = [callLog.outcome_label];
      if (callLog.created_at_display) {
        segments.push(callLog.created_at_display);
      }
      if (callLog.staff_user) {
        segments.push(callLog.staff_user);
      }
      return segments.join(" · ");
    };

    const setQuickLogFeedback = (rowEl, message) => {
      const feedbackEl = rowEl?.querySelector("[data-quick-log-feedback]");
      if (!feedbackEl) {
        return;
      }
      feedbackEl.textContent = message || "";
      feedbackEl.hidden = !message;
    };

    const setQuickLogSubmitting = (rowEl, isSubmitting, activeButton = null) => {
      rowEl.dataset.quickLogSubmitting = isSubmitting ? "true" : "false";
      rowEl.querySelectorAll("[data-quick-log-button]").forEach((button) => {
        button.disabled = isSubmitting;
        button.classList.toggle("is-loading", Boolean(isSubmitting && activeButton === button));
      });
    };

    const updateRowCallSummary = (rowEl, payload) => {
      const summary = payload?.call_summary || {};
      const display = getCallStatusDisplay(summary.status, summary.failed_attempt_count);
      const statusPill = rowEl.querySelector("[data-status-pill]");
      if (statusPill) {
        statusPill.textContent = display.label;
        statusPill.dataset.tone = display.tone;
      }
      const latestCallEl = rowEl.querySelector("[data-latest-call-copy]");
      if (latestCallEl) {
        latestCallEl.textContent = formatLatestCallCopy(payload?.call_log);
        latestCallEl.dataset.tone = display.tone;
      }
    };

    const closeOpenRow = (row) => {
      if (!row) {
        return;
      }
      row.classList.remove("is-open");
      row.querySelector("[data-compact-toggle]")?.setAttribute("aria-expanded", "false");
      const detailEl = row.querySelector("[data-compact-details]");
      if (detailEl) {
        detailEl.hidden = true;
      }
    };

    listEl?.addEventListener("click", (event) => {
      const toggle = event.target.closest("[data-compact-toggle]");
      if (!toggle || !listEl.contains(toggle)) {
        return;
      }

      const rowEl = toggle.closest("[data-calls-sheet-row]");
      if (!rowEl) {
        return;
      }

      const isOpen = rowEl.classList.contains("is-open");
      listEl.querySelectorAll("[data-calls-sheet-row].is-open").forEach((openRow) => {
        if (openRow !== rowEl) {
          closeOpenRow(openRow);
        }
      });

      if (isOpen) {
        closeOpenRow(rowEl);
        return;
      }

      rowEl.classList.add("is-open");
      toggle.setAttribute("aria-expanded", "true");
      const detailEl = rowEl.querySelector("[data-compact-details]");
      if (detailEl) {
        detailEl.hidden = false;
      }
    });

    listEl?.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-quick-log-button]");
      if (!button || !listEl.contains(button)) {
        return;
      }

      event.preventDefault();
      const rowEl = button.closest("[data-calls-sheet-row]");
      if (!rowEl || rowEl.dataset.quickLogSubmitting === "true") {
        return;
      }

      const callUrl = rowEl.dataset.callUrl;
      const primaryTaskId = rowEl.dataset.primaryTaskId;
      const outcome = button.dataset.outcome;
      if (!callUrl || !primaryTaskId || !outcome) {
        setQuickLogFeedback(rowEl, "Quick log is not configured for this case.");
        return;
      }

      setQuickLogFeedback(rowEl, "");
      setQuickLogSubmitting(rowEl, true, button);

      try {
        const response = await fetch(callUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCookie("csrftoken"),
            "X-Requested-With": "XMLHttpRequest",
            Accept: "application/json",
          },
          body: new URLSearchParams({
            task: primaryTaskId,
            outcome,
            notes: "",
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.message || "Could not log call outcome.");
        }
        updateRowCallSummary(rowEl, payload);
      } catch (error) {
        setQuickLogFeedback(rowEl, error?.message || "Could not log call outcome.");
      } finally {
        setQuickLogSubmitting(rowEl, false, button);
      }
    });

  })();
