(() => {
    const summarySelector = "[data-dashboard-summary-grid]";
    const rootSelector = "[data-upcoming-schedule]";
    const triggerSelector = "[data-upcoming-day-trigger]";
    const panelSelector = "[data-upcoming-day-panel]";
    const weekLinkSelector = "[data-upcoming-week-link]";
    let activeNavigationController = null;

    const getElements = () => ({
      summary: document.querySelector(summarySelector),
      root: document.querySelector(rootSelector),
    });

    const setLoadingState = (isLoading) => {
      const { summary, root } = getElements();
      if (summary) {
        summary.classList.toggle("is-loading", isLoading);
        summary.setAttribute("aria-busy", isLoading ? "true" : "false");
      }
      if (root) {
        root.classList.toggle("is-loading", isLoading);
        root.setAttribute("aria-busy", isLoading ? "true" : "false");
        root.querySelectorAll(weekLinkSelector).forEach((link) => {
          link.setAttribute("aria-disabled", isLoading ? "true" : "false");
          link.tabIndex = isLoading ? -1 : 0;
        });
      }
    };

    const setActiveDay = (root, dateKey) => {
      const triggers = Array.from(root.querySelectorAll(triggerSelector));
      const panels = Array.from(root.querySelectorAll(panelSelector));
      if (!triggers.length || !panels.length) {
        return;
      }

      triggers.forEach((trigger) => {
        const isActive = trigger.dataset.upcomingDayTrigger === dateKey;
        trigger.classList.toggle("is-active", isActive);
        trigger.setAttribute("aria-selected", isActive ? "true" : "false");
      });

      panels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.upcomingDayPanel === dateKey);
      });
    };

    const shouldHandleNavigation = (event) => {
      if (event.defaultPrevented) {
        return false;
      }
      if (event.button !== 0) {
        return false;
      }
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return false;
      }
      return true;
    };

    const replaceUpcomingSections = (htmlText) => {
      const parsed = new DOMParser().parseFromString(htmlText, "text/html");
      const nextSummary = parsed.querySelector(summarySelector);
      const nextRoot = parsed.querySelector(rootSelector);
      if (!nextSummary || !nextRoot) {
        throw new Error("Could not refresh the upcoming schedule.");
      }

      const { summary, root } = getElements();
      summary?.replaceWith(nextSummary);
      root?.replaceWith(nextRoot);
      initializeUpcomingSchedule();
      nextRoot
        .querySelector(".upcoming-schedule-control.is-active, .upcoming-schedule-control[aria-current='page']")
        ?.focus({ preventScroll: true });
    };

    const navigateWeek = async (targetUrl, { pushState = true } = {}) => {
      const resolvedUrl = new URL(targetUrl, window.location.href);
      activeNavigationController?.abort();
      const controller = new AbortController();
      activeNavigationController = controller;
      setLoadingState(true);

      try {
        const response = await fetch(resolvedUrl, {
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}.`);
        }

        replaceUpcomingSections(await response.text());
        if (pushState && window.location.href !== resolvedUrl.href) {
          window.history.pushState({ upcomingWeekUrl: resolvedUrl.href }, "", resolvedUrl.href);
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }
        window.location.assign(resolvedUrl.href);
      } finally {
        if (activeNavigationController === controller) {
          activeNavigationController = null;
          setLoadingState(false);
        }
      }
    };

    const initializeUpcomingSchedule = () => {
      const { root } = getElements();
      if (!root || root.dataset.upcomingScheduleBound === "true") {
        return;
      }
      root.dataset.upcomingScheduleBound = "true";

      root.addEventListener("click", (event) => {
        const weekLink = event.target.closest(weekLinkSelector);
        if (weekLink && root.contains(weekLink)) {
          if (!shouldHandleNavigation(event)) {
            return;
          }
          event.preventDefault();
          navigateWeek(weekLink.href);
          return;
        }

        const trigger = event.target.closest(triggerSelector);
        if (!trigger || !root.contains(trigger)) {
          return;
        }

        setActiveDay(root, trigger.dataset.upcomingDayTrigger);
        trigger.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      });
    };

    window.addEventListener("popstate", () => {
      if (!document.querySelector(rootSelector)) {
        return;
      }
      navigateWeek(window.location.href, { pushState: false });
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initializeUpcomingSchedule, { once: true });
    } else {
      initializeUpcomingSchedule();
    }
  })();
