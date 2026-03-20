(() => {
  const shell = document.querySelector("[data-case-detail-shell]");
  if (!shell) {
    return;
  }

  const composer = shell.querySelector("[data-case-composer]");
  const composerButtons = Array.from(shell.querySelectorAll("[data-case-composer-trigger]"));
  const composerPanels = Array.from(shell.querySelectorAll("[data-case-composer-panel]"));
  const composerCloseButtons = Array.from(shell.querySelectorAll("[data-case-composer-close]"));
  const taskFilters = Array.from(shell.querySelectorAll("[data-task-filter]"));
  const allTaskScope = shell.querySelector(".case-detail-all-tasks");
  const taskItems = allTaskScope ? Array.from(allTaskScope.querySelectorAll("[data-task-bucket]")) : [];
  const allTaskEmpty = shell.querySelector("#all-task-empty");
  const allTaskTable = shell.querySelector("#all-task-table");
  const allTaskTableShell = allTaskTable?.closest(".case-task-table-shell") || null;
  const allTaskMobileList = shell.querySelector("#all-task-mobile-list");
  const allTaskToggle = shell.querySelector("[data-all-task-toggle]");
  const allTaskToggleLabel = shell.querySelector("[data-all-task-toggle-label]");
  const allTaskBody = shell.querySelector("[data-all-task-body]");
  const taskEditorHome = shell.querySelector("[data-task-editor-home]");
  const taskEditor = shell.querySelector("[data-task-editor]");
  const taskEditorSlotRows = Array.from(shell.querySelectorAll("[data-task-editor-slot-row]"));
  const taskEditorTriggers = Array.from(shell.querySelectorAll("[data-task-editor-trigger]"));
  const taskEditorCloseButtons = Array.from(shell.querySelectorAll("[data-task-editor-close]"));
  const taskEditorLabel = shell.querySelector("[data-task-editor-label]");
  const taskEditorTitle = shell.querySelector("[data-task-editor-title]");
  const taskEditorSubtitle = shell.querySelector("[data-task-editor-subtitle]");
  const taskEditorActiveTask = shell.querySelector("[data-task-editor-active-task]");
  const taskEditorRescheduleForm = shell.querySelector("[data-task-editor-form='reschedule']");
  const taskEditorNoteForm = shell.querySelector("[data-task-editor-form='note']");
  const taskEditorDateInput = shell.querySelector("#task-shared-reschedule-date");
  const taskEditorNoteInput = shell.querySelector("#task-shared-note");
  const logJumps = Array.from(shell.querySelectorAll(".log-jump"));
  const jumpButtons = Array.from(shell.querySelectorAll("[data-case-jump]"));
  const timeline = shell.querySelector("#clinical-timeline");
  const timelineBody = shell.querySelector("#clinical-timeline-body");
  const feedback = shell.querySelector("[data-case-feedback]");
  const ajaxForms = Array.from(shell.querySelectorAll("[data-case-ajax-form='true']"));

  const taskEditorCopy = {
    reschedule: {
      label: "Reschedule",
      title: "Move follow-up date",
    },
    note: {
      label: "Task note",
      title: "Capture task context",
    },
  };

  const setComposer = (value) => {
    const next = value || "";
    if (composer) {
      composer.hidden = !next;
      composer.dataset.caseActivePane = next;
    }
    composerButtons.forEach((button) => {
      const active = button.dataset.caseComposerTrigger === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.setAttribute("aria-expanded", active ? "true" : "false");
    });
    composerPanels.forEach((panel) => {
      panel.classList.toggle("is-active", panel.dataset.caseComposerPanel === next);
    });
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
    if (allTaskTableShell) {
      allTaskTableShell.classList.toggle("d-none", visibleCount === 0);
    }
    if (allTaskMobileList) {
      allTaskMobileList.classList.toggle("d-none", visibleCount === 0);
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

  const setAllTaskOpen = (open) => {
    if (!allTaskToggle || !allTaskBody) {
      return;
    }

    allTaskBody.hidden = !open;
    allTaskToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (allTaskToggleLabel) {
      allTaskToggleLabel.textContent = open ? "Hide list" : "Show list";
    }
    if (open) {
      filterTasks();
    }
  };

  const clearTaskEditorTriggers = () => {
    taskEditorTriggers.forEach((button) => {
      button.classList.remove("is-active");
      button.setAttribute("aria-expanded", "false");
    });
  };

  const hideTaskEditorSlots = () => {
    taskEditorSlotRows.forEach((row) => {
      row.hidden = true;
    });
  };

  const moveTaskEditorHome = () => {
    hideTaskEditorSlots();
    if (taskEditor && taskEditorHome && taskEditor.parentElement !== taskEditorHome) {
      taskEditorHome.appendChild(taskEditor);
    }
  };

  const readTaskNote = (trigger) => {
    const noteSourceId = trigger?.dataset.taskNoteSource;
    if (!noteSourceId) {
      return "";
    }

    const source = document.getElementById(noteSourceId);
    return source ? source.value : "";
  };

  const hideTaskEditorForms = () => {
    if (taskEditorRescheduleForm) {
      taskEditorRescheduleForm.hidden = true;
      taskEditorRescheduleForm.action = "";
    }
    if (taskEditorNoteForm) {
      taskEditorNoteForm.hidden = true;
      taskEditorNoteForm.action = "";
    }
  };

  const placeTaskEditor = (trigger) => {
    if (!taskEditor || !trigger) {
      return;
    }

    hideTaskEditorSlots();
    const targetId = trigger.dataset.taskEditorTarget;
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) {
      moveTaskEditorHome();
      return;
    }

    const targetRow = target.closest("[data-task-editor-slot-row]");
    if (targetRow) {
      targetRow.hidden = false;
    }

    if (taskEditor.parentElement !== target) {
      target.appendChild(taskEditor);
    }
  };

  const setTaskEditor = (mode, trigger = null) => {
    if (!taskEditor) {
      return;
    }

    const nextMode = mode || "";
    if (!nextMode || !trigger) {
      taskEditor.hidden = true;
      taskEditor.dataset.taskEditorMode = "";
      taskEditor.dataset.mode = "";
      taskEditor.dataset.taskId = "";
      if (taskEditorActiveTask) {
        taskEditorActiveTask.hidden = true;
        taskEditorActiveTask.textContent = "";
      }
      if (taskEditorDateInput) {
        taskEditorDateInput.value = "";
      }
      if (taskEditorNoteInput) {
        taskEditorNoteInput.value = "";
      }
      hideTaskEditorForms();
      clearTaskEditorTriggers();
      moveTaskEditorHome();
      return;
    }

    const copy = taskEditorCopy[nextMode];
    if (!copy) {
      return;
    }

    taskEditor.hidden = false;
    taskEditor.dataset.taskEditorMode = nextMode;
    taskEditor.dataset.mode = nextMode;
    taskEditor.dataset.taskId = trigger.dataset.taskId || "";

    if (taskEditorLabel) {
      taskEditorLabel.textContent = copy.label;
    }
    if (taskEditorTitle) {
      taskEditorTitle.textContent = copy.title;
    }
    if (taskEditorSubtitle) {
      taskEditorSubtitle.textContent = copy.subtitle || "";
      taskEditorSubtitle.hidden = !copy.subtitle;
    }
    if (taskEditorActiveTask) {
      taskEditorActiveTask.hidden = false;
      taskEditorActiveTask.textContent = trigger.dataset.taskTitle || "";
    }

    hideTaskEditorForms();
    clearTaskEditorTriggers();
    placeTaskEditor(trigger);
    trigger.classList.add("is-active");
    trigger.setAttribute("aria-expanded", "true");

    if (nextMode === "reschedule" && taskEditorRescheduleForm) {
      taskEditorRescheduleForm.hidden = false;
      taskEditorRescheduleForm.action = trigger.dataset.taskRescheduleUrl || "";
      if (taskEditorDateInput) {
        taskEditorDateInput.value = trigger.dataset.taskDueDate || "";
      }
    }

    if (nextMode === "note" && taskEditorNoteForm) {
      taskEditorNoteForm.hidden = false;
      taskEditorNoteForm.action = trigger.dataset.taskNoteUrl || "";
      if (taskEditorNoteInput) {
        taskEditorNoteInput.value = readTaskNote(trigger);
      }
    }

    window.requestAnimationFrame(() => {
      if (window.matchMedia("(max-width: 640px)").matches) {
        taskEditor.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      if (nextMode === "reschedule" && taskEditorDateInput) {
        taskEditorDateInput.focus();
      }
      if (nextMode === "note" && taskEditorNoteInput) {
        taskEditorNoteInput.focus();
      }
    });
  };

  composerButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const nextPane = button.dataset.caseComposerTrigger;
      const shouldCollapse = composer?.dataset.caseActivePane === nextPane;
      setComposer(shouldCollapse ? "" : nextPane);
      if (!shouldCollapse && window.matchMedia("(max-width: 991.98px)").matches) {
        window.requestAnimationFrame(() => {
          scrollToSection("#action-center");
        });
      }
    });
  });

  composerCloseButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setComposer("");
    });
  });

  taskEditorTriggers.forEach((button) => {
    button.addEventListener("click", () => {
      const isSameTask = taskEditor?.dataset.taskId === (button.dataset.taskId || "");
      const isSameMode = taskEditor?.dataset.taskEditorMode === button.dataset.taskEditorTrigger;
      const shouldCollapse = !taskEditor?.hidden && isSameTask && isSameMode;
      setTaskEditor(shouldCollapse ? "" : button.dataset.taskEditorTrigger, shouldCollapse ? null : button);
    });
  });

  taskEditorCloseButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setTaskEditor("");
    });
  });

  if (allTaskToggle) {
    allTaskToggle.addEventListener("click", () => {
      const nextOpen = allTaskBody?.hidden ?? true;
      setAllTaskOpen(nextOpen);
    });
  }

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
        if (form.closest("[data-task-editor]")) {
          setTaskEditor("");
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

  setComposer("");
  setTaskEditor("");
  setAllTaskOpen(false);
  filterTasks();
})();
