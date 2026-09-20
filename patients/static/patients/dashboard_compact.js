(() => {
    const mobileBreakpoint = window.matchMedia("(max-width: 767.98px)");
    const measureCanvas = document.createElement("canvas");
    const measureContext = measureCanvas.getContext("2d");

    const pendingScopes = new Set();
    let measureFrame = null;
    const applyCompactNameFallback = (scope = document) => {
      pendingScopes.add(scope);
      if (measureFrame !== null) return;
      measureFrame = window.requestAnimationFrame(() => {
        measureFrame = null;
        const names = new Set();
        pendingScopes.forEach((root) => root.querySelectorAll("[data-compact-name]").forEach((name) => names.add(name)));
        pendingScopes.clear();
        names.forEach((name) => {
          name.textContent = name.dataset.fullName || name.textContent || "";
          name.setAttribute("title", name.textContent);
        });
        if (!mobileBreakpoint.matches) return;
        const shortened = [];
        names.forEach((name) => {
          if (!name.getClientRects().length) return;
          const style = window.getComputedStyle(name);
          if (measureContext) measureContext.font = [style.fontStyle, style.fontVariant, style.fontWeight, style.fontSize, style.fontFamily].join(" ");
          const fullWidth = measureContext ? measureContext.measureText(name.textContent).width : name.scrollWidth;
          const line = name.closest(".dashboard-compact-summary");
          if ((line && line.scrollWidth > line.clientWidth + 1) || fullWidth > name.clientWidth + 1) shortened.push(name);
        });
        shortened.forEach((name) => { name.textContent = name.dataset.shortName || name.textContent; });
      });
    };

    const syncCompactModule = (module) => {
      const rows = Array.from(module.querySelectorAll("[data-compact-row]"));
      const limit = Number(module.dataset.compactLimit || "10");
      const isExpanded = module.dataset.compactExpanded === "true";
      const expandButton = module.querySelector("[data-compact-expand]");

      rows.forEach((row, index) => {
        row.hidden = !isExpanded && index >= limit;
      });

      const hiddenOpenRow = module.querySelector("[data-compact-row].is-open[hidden]");
      if (hiddenOpenRow) {
        hiddenOpenRow.classList.remove("is-open");
        const hiddenToggle = hiddenOpenRow.querySelector("[data-compact-toggle]");
        const hiddenDetails = hiddenOpenRow.querySelector("[data-compact-details]");
        if (hiddenToggle) {
          hiddenToggle.setAttribute("aria-expanded", "false");
        }
        if (hiddenDetails) {
          hiddenDetails.hidden = true;
        }
      }

      if (expandButton) {
        if (rows.length <= limit) {
          expandButton.hidden = true;
        } else {
          expandButton.hidden = false;
          expandButton.textContent = isExpanded ? "Collapse list" : `Expand ${rows.length - limit} more`;
          expandButton.setAttribute("aria-expanded", isExpanded ? "true" : "false");
        }
      }

      applyCompactNameFallback(module);
    };

    const initializeCompactModules = () => {
      document.querySelectorAll("[data-compact-module]").forEach((module) => {
        if (module.dataset.compactBound === "true") {
          return;
        }
        module.dataset.compactBound = "true";
        module.dataset.compactExpanded = "false";

        module.addEventListener("click", (event) => {
          const expandButton = event.target.closest("[data-compact-expand]");
          if (expandButton && module.contains(expandButton)) {
            module.dataset.compactExpanded = module.dataset.compactExpanded === "true" ? "false" : "true";
            syncCompactModule(module);
            return;
          }

          const toggle = event.target.closest("[data-compact-toggle]");
          if (!toggle || !module.contains(toggle)) {
            return;
          }

          const row = toggle.closest("[data-compact-row]");
          const isOpen = row && row.classList.contains("is-open");
          module.querySelectorAll("[data-compact-row].is-open").forEach((openRow) => {
            openRow.classList.remove("is-open");
            const openToggle = openRow.querySelector("[data-compact-toggle]");
            const openDetails = openRow.querySelector("[data-compact-details]");
            if (openToggle) {
              openToggle.setAttribute("aria-expanded", "false");
            }
            if (openDetails) {
              openDetails.hidden = true;
            }
          });

          if (row && !isOpen) {
            row.classList.add("is-open");
            toggle.setAttribute("aria-expanded", "true");
            const details = row.querySelector("[data-compact-details]");
            if (details) {
              details.hidden = false;
            }
            row.dispatchEvent(new CustomEvent("dashboardcompactopen", { bubbles: true }));
          }

          syncCompactModule(module);
        });

        syncCompactModule(module);
      });
    };

    const initializeInlineCallReveals = () => {
      if (document.body.dataset.callRevealBound === "true") {
        return;
      }
      document.body.dataset.callRevealBound = "true";

      const closeCallRevealScope = (scope) => {
        if (!scope) {
          return;
        }

        const trigger = scope.querySelector("[data-call-reveal-trigger]");
        const reveal = scope.querySelector("[data-call-reveal]");
        if (trigger) {
          trigger.hidden = false;
          trigger.setAttribute("aria-expanded", "false");
        }
        if (reveal) {
          reveal.hidden = true;
        }
        scope.classList.remove("is-open");
      };

      const closeAllCallReveals = (exceptScope = null) => {
        document.querySelectorAll("[data-call-reveal-scope]").forEach((scope) => {
          if (scope !== exceptScope) {
            closeCallRevealScope(scope);
          }
        });
      };

      document.addEventListener("click", (event) => {
        const closeButton = event.target.closest("[data-call-reveal-close]");
        if (closeButton) {
          event.preventDefault();
          event.stopPropagation();
          closeCallRevealScope(closeButton.closest("[data-call-reveal-scope]"));
          return;
        }

        const trigger = event.target.closest("[data-call-reveal-trigger]");
        if (trigger) {
          event.preventDefault();
          event.stopPropagation();

          const scope = trigger.closest("[data-call-reveal-scope]");
          const targetId = trigger.getAttribute("aria-controls");
          if (!scope || !targetId) {
            return;
          }

          const reveal = document.getElementById(targetId);
          if (!reveal) {
            return;
          }

          const isOpen = !reveal.hidden;
          closeAllCallReveals(scope);
          if (isOpen) {
            closeCallRevealScope(scope);
            return;
          }

          trigger.hidden = true;
          trigger.setAttribute("aria-expanded", "true");
          reveal.hidden = false;
          scope.classList.add("is-open");
          return;
        }

        if (event.target.closest("[data-call-reveal-scope]")) {
          return;
        }

        closeAllCallReveals();
      });

      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          closeAllCallReveals();
        }
      });
    };

    window.dashboardCompactUI = { applyCompactNameFallback };

    const initialize = () => {
      initializeCompactModules();
      initializeInlineCallReveals();
      applyCompactNameFallback(document);
    };

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initialize, { once: true });
    } else {
      initialize();
    }

    window.addEventListener("resize", () => applyCompactNameFallback(document));
  })();
