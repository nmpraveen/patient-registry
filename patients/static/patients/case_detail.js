(() => {
  const shell = document.querySelector("[data-case-detail-shell]");
  if (!shell) {
    return;
  }

  const composer = shell.querySelector("[data-case-composer]");
  const composerButtons = Array.from(shell.querySelectorAll("[data-case-composer-trigger]"));
  const composerPanels = Array.from(shell.querySelectorAll("[data-case-composer-panel]"));
  const taskFilters = Array.from(shell.querySelectorAll("[data-task-filter]"));
  const allTaskScope = shell.querySelector(".case-detail-all-tasks");
  const taskItems = allTaskScope ? Array.from(allTaskScope.querySelectorAll("[data-task-bucket]")) : [];
  const allTaskEmpty = shell.querySelector("#all-task-empty");
  const allTaskTable = shell.querySelector("#all-task-table");
  const logJumps = Array.from(shell.querySelectorAll(".log-jump"));
  const jumpButtons = Array.from(shell.querySelectorAll("[data-case-jump]"));
  const timeline = shell.querySelector("#clinical-timeline");
  const timelineBody = shell.querySelector("#clinical-timeline-body");
  const feedback = shell.querySelector("[data-case-feedback]");
  const ajaxForms = Array.from(shell.querySelectorAll("[data-case-ajax-form='true']"));
  const storageKey = "medtrack.caseDetail.activeComposer";

  const readStoredComposer = () => {
    try {
      return window.localStorage.getItem(storageKey) || "task";
    } catch {
      return "task";
    }
  };

  const writeStoredComposer = (value) => {
    try {
      window.localStorage.setItem(storageKey, value);
    } catch {
      // Ignore storage failures and keep state session-local.
    }
  };

  const setComposer = (value) => {
    const next = value || "task";
    if (composer) {
      composer.dataset.caseActivePane = next;
    }
    composerButtons.forEach((button) => {
      const active = button.dataset.caseComposerTrigger === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    composerPanels.forEach((panel) => {
      panel.classList.toggle("is-active", panel.dataset.caseComposerPanel === next);
    });
    writeStoredComposer(next);
  };

  const filterTasks = () => {
    if (!taskFilters.length || !taskItems.length) {
      return;
    }

    const selected = new Set(taskFilters.filter((input) => input.checked).map((input) => input.value));
    let visibleCount = 0;

    taskItems.forEach((item) => {
      const visible = selected.has(item.dataset.taskBucket);
      item.classList.toggle("d-none", !visible);
      if (visible) {
        visibleCount += 1;
      }
    });

    if (allTaskEmpty) {
      allTaskEmpty.classList.toggle("d-none", visibleCount > 0);
    }
    if (allTaskTable) {
      allTaskTable.classList.toggle("d-none", visibleCount === 0);
    }
  };

  const feedbackMarkup = (lines) => lines.map((line) => `<div>${line}</div>`).join("");

  const collectErrors = (errors) => {
    if (!errors || typeof errors !== "object") {
      return [];
    }

    return Object.values(errors).flatMap((value) => {
      if (Array.isArray(value)) {
        return value.map((item) => {
          if (typeof item === "string") {
            return item;
          }
          if (item && typeof item === "object" && "message" in item) {
            return item.message;
          }
          return "";
        });
      }
      return [];
    }).filter(Boolean);
  };

  const showFeedback = (variant, message, errors = []) => {
    if (!feedback) {
      return;
    }

    feedback.hidden = false;
    feedback.className = `case-detail-feedback alert alert-${variant === "error" ? "danger" : "success"}`;
    feedback.innerHTML = feedbackMarkup([message, ...errors]);
  };

  const clearFeedback = () => {
    if (!feedback) {
      return;
    }
    feedback.hidden = true;
    feedback.className = "case-detail-feedback";
    feedback.innerHTML = "";
  };

  const scrollToSection = (selector) => {
    const target = shell.querySelector(selector);
    if (!target) {
      return;
    }

    target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  composerButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setComposer(button.dataset.caseComposerTrigger);
      if (window.matchMedia("(max-width: 991.98px)").matches) {
        scrollToSection("[data-case-composer]");
      }
    });
  });

  jumpButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.caseJump;
      if (target === "timeline") {
        scrollToSection("#clinical-timeline");
        if (timelineBody && !timelineBody.classList.contains("show")) {
          window.bootstrap?.Collapse?.getOrCreateInstance(timelineBody)?.show();
        }
      } else if (target === "tasks") {
        scrollToSection(".case-detail-tasks");
      }
    });
  });

  logJumps.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      if (timelineBody && !timelineBody.classList.contains("show")) {
        window.bootstrap?.Collapse?.getOrCreateInstance(timelineBody)?.show();
      }
      if (timeline) {
        timeline.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      const href = link.getAttribute("href");
      if (href) {
      window.history.replaceState({}, "", href);
      }
    });
  });

  ajaxForms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.caseSubmitting === "true") {
        return;
      }

      clearFeedback();
      form.dataset.caseSubmitting = "true";
      const submitButtons = Array.from(form.querySelectorAll("button[type='submit']"));
      submitButtons.forEach((button) => {
        button.disabled = true;
      });

      try {
        const response = await fetch(form.action, {
          method: form.method || "POST",
          body: new FormData(form),
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "application/json",
          },
        });
        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
          showFeedback("error", payload.message || "Could not save changes.", collectErrors(payload.errors));
          return;
        }

        showFeedback("success", payload.message || "Saved.");
        if (form.closest("[data-case-composer-panel]")) {
          form.reset();
        }
        window.setTimeout(() => {
          window.location.reload();
        }, 300);
      } catch {
        showFeedback("error", "The update could not be completed. Please try again.");
      } finally {
        delete form.dataset.caseSubmitting;
        submitButtons.forEach((button) => {
          button.disabled = false;
        });
      }
    });
  });

  taskFilters.forEach((input) => {
    input.addEventListener("change", filterTasks);
  });

  setComposer(readStoredComposer());
  filterTasks();
})();
