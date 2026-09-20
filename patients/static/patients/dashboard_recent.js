(() => {
      const initializeRecentCases = () => {
        const payloadEl = document.getElementById("recent-cases-payload");
        const endpointsEl = document.getElementById("recent-case-endpoints");
        const panelEl = document.querySelector("[data-recent-case-panel]");
        const rowList = document.querySelector("[data-recent-case-list]");
        const toggleButton = document.querySelector("[data-recent-case-toggle]");
        const categoryIconTemplates = new Map(
          Array.from(document.querySelectorAll("[data-dashboard-icon-template]")).map((template) => [
            template.dataset.dashboardIconTemplate,
            template.innerHTML.trim(),
          ]),
        );
        if (!payloadEl || !endpointsEl || !panelEl || !rowList || panelEl.dataset.recentCaseBound === "true") {
          return;
        }
        panelEl.dataset.recentCaseBound = "true";

        const initialCases = JSON.parse(payloadEl.textContent || "[]");
        const caseStore = new Map(initialCases.map((entry) => [entry.id, entry]));
        const pendingDetails = new Map();
        const moreButton = panelEl.querySelector("[data-recent-case-more]");
        let nextCursor = endpointsEl.dataset.nextCursor || "";
        let loadingPage = false;
        const listLimit = Number(panelEl.dataset.compactLimit || "10");
        const listUrl = endpointsEl.dataset.listUrl;
        const updateUrlTemplate = endpointsEl.dataset.updateUrlTemplate;

        let listExpanded = false;
        let openCaseId = null;

        const escapeHtml = (value) =>
          String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");

        const clampReplaceId = (template, id) => template.replace("/0/", `/${id}/`);

        const renderInlineDashboardIcon = ({
          label = "",
          iconPath = "",
          extraClass = "",
          dataAttribute = "data-category-icon-path",
        } = {}) => {
          const iconMarkup = categoryIconTemplates.get(iconPath) || "";
          const fallback = String(label).slice(0, 2).toUpperCase();
          const iconPathAttribute = iconPath ? ` ${dataAttribute}="${escapeHtml(iconPath)}"` : "";
          return `
            <span class="dashboard-category-inline-icon ${extraClass}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"${iconPathAttribute}>
              <span class="dashboard-category-icon-glyph">
                ${iconMarkup || `<span class="dashboard-row-category-fallback">${escapeHtml(fallback)}</span>`}
              </span>
              <span class="dashboard-category-icon-label">${escapeHtml(label)}</span>
            </span>
          `;
        };

        const renderRecentContextIcon = (entry, extraClass = "") => {
          if (entry.subcategory_name) {
            return renderInlineDashboardIcon({
              label: entry.subcategory_name,
              iconPath: entry.subcategory_icon_path || "",
              extraClass,
              dataAttribute: "data-subcategory-icon-path",
            });
          }
          if (entry.category_name) {
            return renderInlineDashboardIcon({
              label: entry.category_name,
              iconPath: entry.category_icon_path || "",
              extraClass,
            });
          }
          return "";
        };

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

        const handleJsonResponse = async (response) => {
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(payload.message || "Request failed.");
          }
          return payload;
        };

        const postForm = async (url, formData) => {
          const response = await fetch(url, {
            method: "POST",
            headers: {
              "X-CSRFToken": getCookie("csrftoken"),
              "X-Requested-With": "XMLHttpRequest",
              Accept: "application/json",
            },
            body: formData,
          });
          return handleJsonResponse(response);
        };

        const upsertCase = (entry) => {
          if (!entry || typeof entry.id !== "number") {
            return;
          }
          caseStore.set(entry.id, entry);

        };

        const renderTasks = (entry) => {
          if (!Array.isArray(entry.tasks)) {
            return '<div class="dashboard-module-empty">Loading tasks...</div>';
          }
          const tasks = entry.tasks;
          if (!tasks.length) {
            return '<div class="dashboard-module-empty">No tasks available.</div>';
          }
          return `
            <div class="dashboard-compact-task-list">
              ${tasks
                .map(
                  (task) => `
                    <article class="dashboard-compact-task">
                      <div class="dashboard-compact-task-title">${escapeHtml(task.title)}</div>
                      ${task.can_edit ? `<a class="btn btn-sm btn-outline-primary" href="${escapeHtml(task.edit_url)}">Edit</a>` : ""}
                      <div class="dashboard-compact-task-meta">
                        <span>Due ${escapeHtml(task.due_date_display)}</span>
                        <span>${escapeHtml(task.status_label)}</span>
                      </div>
                      ${
                        task.notes
                          ? `<div class="dashboard-compact-task-note">Notes: ${escapeHtml(task.notes)}</div>`
                          : ""
                      }
                    </article>
                  `,
                )
                .join("")}
            </div>
          `;
        };

        const renderRecentDetail = (entry, feedback = null) => `
          <div class="dashboard-compact-detail-header">
            <span class="dashboard-compact-detail-label">Notes</span>
            <div class="dashboard-compact-detail-pills">
              ${
                renderRecentContextIcon(
                  entry,
                  entry.subcategory_name ? "dashboard-compact-subcategory" : "",
                )
              }
              <a class="dashboard-compact-detail-pill-link" href="${escapeHtml(entry.detail_url)}" data-compact-action>Open case</a>
            </div>
          </div>
          <div class="dashboard-compact-feedback alert alert-${feedback ? feedback.level : "success"}${feedback ? "" : " is-hidden"}">${
            feedback ? escapeHtml(feedback.message) : ""
          }</div>
          <form class="dashboard-compact-notes-form" data-recent-case-form data-case-id="${entry.id}">
            <input type="hidden" name="notes_baseline" value="${escapeHtml(entry.notes_baseline || "")}">
            <div>
              <label class="visually-hidden" for="recent-case-notes-${entry.id}">Notes</label>
              <textarea class="form-control form-control-sm" id="recent-case-notes-${entry.id}" name="notes" rows="3"${
                entry.can_edit ? "" : " readonly"
              }>${escapeHtml(entry.notes || "")}</textarea>
            </div>
            <div class="dashboard-compact-notes-actions">
              ${
                entry.can_edit
                  ? '<button type="submit" class="btn btn-sm btn-primary">Save notes</button>'
                  : '<span class="dashboard-compact-readonly">Reception access is read-only in this panel.</span>'
              }
            </div>
          </form>
          <div class="dashboard-compact-detail-block">
            <span class="dashboard-compact-detail-label">Tasks</span>
            ${renderTasks(entry)}
          </div>
        `;

        const fetchRecentCase = (caseId) => {
          if (!pendingDetails.has(caseId)) {
            const pending = fetch(clampReplaceId(updateUrlTemplate, caseId), {
              headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
            }).then(handleJsonResponse).then((payload) => {
              if (!payload.case || payload.case.id !== caseId) throw new Error("Could not load this case.");
              upsertCase(payload.case);
              return payload.case;
            }).finally(() => pendingDetails.delete(caseId));
            pendingDetails.set(caseId, pending);
          }
          return pendingDetails.get(caseId);
        };

        const showFeedback = (row, message, level = "danger") => {
          const detail = row.querySelector("[data-recent-case-detail]");
          let feedback = detail.querySelector(".dashboard-compact-feedback");
          if (!feedback) {
            feedback = document.createElement("div");
            detail.prepend(feedback);
          }
          feedback.className = `dashboard-compact-feedback alert alert-${level}`;
          feedback.setAttribute("role", "status");
          feedback.textContent = message;
        };

        const closeRecentRow = (row) => {
          if (!row) {
            return;
          }
          row.classList.remove("is-open");
          row.querySelector("[data-recent-case-trigger]")?.setAttribute("aria-expanded", "false");
          const detailEl = row.querySelector("[data-recent-case-detail]");
          if (detailEl) {
            detailEl.hidden = true;
          }
          if (openCaseId === Number(row.dataset.caseId)) {
            openCaseId = null;
          }
        };

        const syncRecentList = () => {
          const rows = Array.from(rowList.querySelectorAll("[data-recent-case-row]"));
          rows.forEach((row, index) => {
            row.hidden = !listExpanded && index >= listLimit;
          });

          const hiddenOpenRow = rowList.querySelector("[data-recent-case-row].is-open[hidden]");
          if (hiddenOpenRow) {
            closeRecentRow(hiddenOpenRow);
          }

          if (toggleButton) {
            if (rows.length <= listLimit) {
              toggleButton.hidden = true;
            } else {
              toggleButton.hidden = false;
              toggleButton.textContent = listExpanded ? "Collapse list" : `Expand ${rows.length - listLimit} more`;
              toggleButton.setAttribute("aria-expanded", listExpanded ? "true" : "false");
            }
          }

          if (moreButton) moreButton.hidden = !listExpanded || !nextCursor;
          window.dashboardCompactUI?.applyCompactNameFallback(panelEl);
        };

        const renderRecentRow = (row, entry, feedback = null) => {
          const detailEl = row.querySelector("[data-recent-case-detail]");
          const summaryEl = row.querySelector(".dashboard-compact-summary");
          if (!detailEl || !summaryEl) {
            return;
          }
          const recentTone = entry.created_tone || "older";
          summaryEl.innerHTML = `
            <span class="dashboard-recent-timeline dashboard-recent-timeline--${escapeHtml(recentTone)}">
              <span class="dashboard-recent-time-badge dashboard-recent-time-badge--${escapeHtml(recentTone)}">${escapeHtml(entry.created_badge_label || entry.created_at_short_display || entry.created_at_display)}</span>
              <span class="dashboard-recent-time-label">${escapeHtml(entry.created_badge_suffix || "ago")}</span>
            </span>
            <span class="dashboard-recent-body">
              <span class="dashboard-recent-main">
                <span class="dashboard-recent-name" data-compact-name data-full-name="${escapeHtml(entry.name)}" data-short-name="${escapeHtml(entry.short_name || entry.first_name || entry.name)}">${escapeHtml(entry.name)}</span>
                ${entry.sex_age && entry.sex_age !== "-" ? `<span class="dashboard-recent-sex-age">${escapeHtml(entry.sex_age)}</span>` : ""}
                ${
                  renderRecentContextIcon(
                    entry,
                    entry.subcategory_name ? "dashboard-recent-category" : "dashboard-recent-category-icon",
                  )
                }
              </span>
              <span class="dashboard-recent-meta">
                <span class="dashboard-recent-diagnosis">${escapeHtml(entry.diagnosis_short || entry.diagnosis || "")}</span>
              </span>
            </span>
            <span class="dashboard-recent-date">${escapeHtml(entry.created_date_label || entry.created_at_short_display || entry.created_at_display)}</span>
          `;
          detailEl.innerHTML = Array.isArray(entry.tasks) ? renderRecentDetail(entry, feedback)
            : '<div class="dashboard-module-empty" role="status">Loading tasks...</div>';
          detailEl.classList.toggle("dashboard-compact-details--with-subcategory", Boolean(entry.subcategory_name));
          row.style.setProperty("--theme-category-bg", entry.category_bg_color || "");
          row.style.setProperty("--theme-category-text", entry.category_text_color || "");
          row.style.setProperty("--theme-category-border", entry.category_border_color || "");

        };

        const hydrateRecentRow = async (row, feedback = null) => {
          const caseId = Number(row.dataset.caseId);
          // Reopening a row must preserve its unsaved textarea and baseline.
          if (!feedback && row.dataset.detailLoaded === "true") return;
          let entry = caseStore.get(caseId);
          if (!entry) return;
          if (!Array.isArray(entry.tasks)) {
            renderRecentRow(row, entry);
            entry = await fetchRecentCase(caseId);
          }
          if (!feedback && row.dataset.detailLoaded === "true") return;
          renderRecentRow(row, entry, feedback);
          row.dataset.detailLoaded = "true";
        };

        const appendSummary = (entry) => {
          if (rowList.querySelector(`[data-case-id="${entry.id}"][data-recent-case-row]`)) return;
          const row = document.createElement("article");
          row.className = "dashboard-compact-row dashboard-recent-row";
          row.dataset.recentCaseRow = "";
          row.dataset.caseId = String(entry.id);
          row.innerHTML = `<div class="dashboard-compact-row-top"><button type="button" class="dashboard-compact-toggle" data-recent-case-trigger data-case-id="${entry.id}" aria-expanded="false" aria-controls="recent-case-detail-${entry.id}"><div class="dashboard-compact-summary dashboard-recent-summary"></div></button></div><div id="recent-case-detail-${entry.id}" class="dashboard-compact-details" data-recent-case-detail hidden></div>`;
          rowList.appendChild(row);
          renderRecentRow(row, entry);
        };

        moreButton?.addEventListener("click", async () => {
          if (!nextCursor || loadingPage) return;
          loadingPage = true;
          moreButton.disabled = true;
          try {
            const params = new URLSearchParams({ cursor: nextCursor, limit: "20" });
            const response = await fetch(`${listUrl}?${params}`, { headers: { Accept: "application/json" } });
            const payload = await handleJsonResponse(response);
            (payload.results || []).forEach((entry) => { upsertCase(entry); appendSummary(entry); });
            nextCursor = payload.next_cursor || "";
            moreButton.textContent = "Load more";
            syncRecentList();
          } catch {
            moreButton.textContent = "Retry loading";
          } finally {
            loadingPage = false;
            moreButton.disabled = false;
          }
        });

        toggleButton?.addEventListener("click", () => {
          listExpanded = !listExpanded;
          syncRecentList();
        });

        rowList.addEventListener("click", async (event) => {
          const trigger = event.target.closest("[data-recent-case-trigger]");
          if (!trigger || !rowList.contains(trigger)) {
            return;
          }

          const row = trigger.closest("[data-recent-case-row]");
          if (!row) {
            return;
          }

          const caseId = Number(row.dataset.caseId);
          const isOpen = row.classList.contains("is-open");
          rowList.querySelectorAll("[data-recent-case-row].is-open").forEach((openRow) => closeRecentRow(openRow));

          if (isOpen) {
            syncRecentList();
            return;
          }

          row.classList.add("is-open");
          trigger.setAttribute("aria-expanded", "true");
          const detailEl = row.querySelector("[data-recent-case-detail]");
          if (detailEl) {
            detailEl.hidden = false;
          }
          openCaseId = caseId;

          try {
            await hydrateRecentRow(row);
          } catch (error) {
            showFeedback(row, error.message);
          }

          syncRecentList();
        });

        rowList.addEventListener("submit", async (event) => {
          const form = event.target.closest("[data-recent-case-form]");
          if (!form) {
            return;
          }
          event.preventDefault();
          if (form.dataset.saving === "true") return;
          form.dataset.saving = "true";
          const notes = form.querySelector("textarea[name=notes]");
          if (notes) notes.readOnly = true;
          const row = form.closest("[data-recent-case-row]");
          const caseId = Number(form.dataset.caseId);
          const submitButton = form.querySelector("button[type='submit']");
          if (submitButton) {
            submitButton.disabled = true;
          }
          try {
            const payload = await postForm(
              clampReplaceId(updateUrlTemplate, caseId),
              new FormData(form),
            );
            if (payload.case) {
              upsertCase(payload.case);
            }
            if (row) {
              await hydrateRecentRow(row, {
                message: payload.message || "Recent case updated.",
                level: "success",
              });
            }
          } catch (error) {
            if (row) {
              showFeedback(row, error.message);
            }
          } finally {
            delete form.dataset.saving;
            if (notes) notes.readOnly = false;
            if (submitButton) {
              submitButton.disabled = false;
            }
          }
        });

        syncRecentList();
      };

      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeRecentCases, { once: true });
      } else {
        initializeRecentCases();
      }
    })();
