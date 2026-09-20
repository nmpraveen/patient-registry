(() => {
          const config = document.getElementById("global-search-script").dataset;
          const input = document.getElementById("global-case-search-input");
          const dropdown = document.getElementById("global-search-dropdown");
          const status = document.getElementById("global-search-status");
          const container = document.getElementById("global-search-container");
          const searchField = container?.querySelector("[data-search-field]");
          const filterToggle = container?.querySelector("[data-search-category-toggle]");
          const filterMenu = container?.querySelector("[data-search-category-menu]");
          const tagsContainer = container?.querySelector("[data-search-selected-tags]");
          const filterCount = container?.querySelector("[data-search-category-count]");
          const categoryButtons = container ? Array.from(container.querySelectorAll("[data-search-category-option]")) : [];
          const patientsLink = document.getElementById("global-patient-list-link");
          const casesLink = document.getElementById("global-case-list-link");
          if (!input || !dropdown || !container) {
            return;
          }

          let activeIndex = -1;
          let currentResults = [];
          let requestGeneration = 0;
          let activeSearchController = null;
          let filterOpen = false;
          let optionSequence = 0;
          const defaultPlaceholder = "Search patients or cases...";
          const filteredPlaceholder = "Search within filters...";
          const allCategoryValues = categoryButtons.map((button) => button.dataset.searchCategoryOption);

          const normalizeCategoryValue = (label) => {
            const normalized = String(label || "")
              .toLowerCase()
              .replace(/[^a-z]/g, "");
            if (normalized === "anc") {
              return "anc";
            }
            if (normalized === "surgery" || normalized === "surgical") {
              return "surgery";
            }
            if (normalized === "medicine" || normalized === "nonsurgical") {
              return "non-surgical";
            }
            return "other";
          };

          const resultsCategoryValue = (value) => {
            if (value === "surgical") {
              return "surgery";
            }
            return value;
          };

          const isButtonSelected = (button) => button.getAttribute("aria-pressed") !== "false";

          const selectedCategories = () => categoryButtons
            .filter((button) => isButtonSelected(button))
            .map((button) => button.dataset.searchCategoryOption);

          const hasNarrowedCategoryFilters = (categories = selectedCategories()) => (
            categories.length > 0 && categories.length < allCategoryValues.length
          );

          const syncSearchFieldState = () => {
            if (!searchField) {
              return;
            }
            searchField.classList.toggle("is-open", filterOpen || !dropdown.hidden);
          };

          const announce = (message) => {
            if (status) {
              status.textContent = message;
            }
          };

          const availableOptions = () => Array.from(dropdown.querySelectorAll('[role="option"]'));

          const setActiveOption = (nextIndex) => {
            const options = availableOptions();
            if (!options.length || nextIndex < 0 || nextIndex >= options.length) {
              activeIndex = -1;
              input.setAttribute("aria-activedescendant", "");
              options.forEach((option) => {
                option.classList.remove("active");
                option.setAttribute("aria-selected", "false");
              });
              return;
            }
            activeIndex = nextIndex;
            options.forEach((option, index) => {
              const isActive = index === activeIndex;
              option.classList.toggle("active", isActive);
              option.setAttribute("aria-selected", isActive ? "true" : "false");
            });
            input.setAttribute("aria-activedescendant", options[activeIndex].id);
          };

          const activateOption = (option) => {
            if (!option) {
              return;
            }
            if (option.dataset.resultsPage) {
              window.location.assign(option.dataset.resultsPage);
              return;
            }
            const result = currentResults[Number(option.dataset.index)];
            if (result?.detail_url) {
              window.location.assign(result.detail_url);
            }
          };

          const closeResults = () => {
            dropdown.hidden = true;
            currentResults = [];
            setActiveOption(-1);
            input.setAttribute("aria-expanded", "false");
            syncSearchFieldState();
          };

          const openResults = () => {
            dropdown.hidden = false;
            input.setAttribute("aria-expanded", "true");
            syncSearchFieldState();
          };

          const setFilterButtonState = (button, isActive) => {
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
            button.classList.toggle("is-inactive", !isActive);
          };

          const appendCategoryGroups = (params, categories) => {
            const narrowed = hasNarrowedCategoryFilters(categories) ? categories : [];
            const categoryGroups = [];
            narrowed.forEach((category) => {
              const normalized = resultsCategoryValue(category);
              if (normalized && !categoryGroups.includes(normalized)) {
                categoryGroups.push(normalized);
              }
            });
            categoryGroups.forEach((group) => params.append("category_group", group));
          };

          const buildPatientResultsUrl = (query) => {
            const params = new URLSearchParams();
            if (query) {
              params.set("q", query);
            }
            return params.toString()
              ? `${config.patientListUrl}?${params.toString()}`
              : `${config.patientListUrl}`;
          };

          const buildCaseResultsUrl = (query, categories) => {
            const params = new URLSearchParams();
            if (query) {
              params.set("q", query);
            }
            appendCategoryGroups(params, categories);
            return params.toString()
              ? `${config.caseListUrl}?${params.toString()}`
              : `${config.caseListUrl}`;
          };

          const buildCasesUrl = (categories) => buildCaseResultsUrl("", categories);

          const syncPatientsLink = () => {
            if (!patientsLink) {
              return;
            }
            patientsLink.href = buildPatientResultsUrl(input.value.trim());
          };

          const syncCasesLink = () => {
            if (!casesLink) {
              return;
            }
            const nextHref = buildCasesUrl(selectedCategories());
            casesLink.href = nextHref;
          };

          const updateFilterToggle = () => {
            if (!filterToggle || !filterCount) {
              return;
            }
            const categories = selectedCategories();
            const narrowed = hasNarrowedCategoryFilters(categories);
            filterToggle.classList.toggle("is-open", filterOpen);
            filterToggle.classList.toggle("has-active-filters", narrowed && !filterOpen);
            filterToggle.setAttribute("aria-expanded", filterOpen ? "true" : "false");
            if (narrowed && !filterOpen) {
              filterCount.hidden = false;
              filterCount.textContent = String(categories.length);
            } else {
              filterCount.hidden = true;
            }
          };

          const renderSelectedTags = () => {
            if (!tagsContainer) {
              return;
            }
            const categories = selectedCategories();
            tagsContainer.replaceChildren();
            if (!hasNarrowedCategoryFilters(categories)) {
              input.placeholder = defaultPlaceholder;
              return;
            }
            input.placeholder = filteredPlaceholder;
            categoryButtons.forEach((button) => {
              if (!isButtonSelected(button)) {
                return;
              }
              const tag = document.createElement("button");
              tag.type = "button";
              tag.className = "global-search-filter-tag";
              tag.dataset.removeCategory = button.dataset.searchCategoryOption;
              if (button.getAttribute("style")) {
                tag.setAttribute("style", button.getAttribute("style"));
              }

              const label = document.createElement("span");
              label.textContent = button.dataset.searchCategoryLabel || "";
              tag.appendChild(label);

              const remove = document.createElement("span");
              remove.className = "global-search-filter-tag-remove";
              remove.setAttribute("aria-hidden", "true");
              remove.textContent = "x";
              tag.appendChild(remove);
              tagsContainer.appendChild(tag);
            });
          };

          const renderFilterButtons = () => {
            categoryButtons.forEach((button) => {
              setFilterButtonState(button, isButtonSelected(button));
            });
          };

          const setFilterOpen = (nextValue) => {
            filterOpen = nextValue;
            if (filterMenu) {
              filterMenu.hidden = !filterOpen;
            }
            updateFilterToggle();
            syncSearchFieldState();
          };

          const appendResultsPageActions = (query, categories) => {
            const patientAction = document.createElement("button");
            patientAction.type = "button";
            patientAction.className = "global-search-item global-search-action";
            patientAction.dataset.resultsPage = buildPatientResultsUrl(query);
            patientAction.id = `global-search-option-${optionSequence}-patients`;
            patientAction.setAttribute("role", "option");
            patientAction.setAttribute("aria-selected", "false");
            patientAction.tabIndex = -1;
            patientAction.textContent = "View patients";
            dropdown.appendChild(patientAction);

            if (!categories.length) {
              return;
            }

            const caseAction = document.createElement("button");
            caseAction.type = "button";
            caseAction.className = "global-search-item global-search-action";
            caseAction.dataset.resultsPage = buildCaseResultsUrl(query, categories);
            caseAction.id = `global-search-option-${optionSequence}-cases`;
            caseAction.setAttribute("role", "option");
            caseAction.setAttribute("aria-selected", "false");
            caseAction.tabIndex = -1;
            caseAction.textContent = "View cases";
            dropdown.appendChild(caseAction);
          };

          const renderResults = (results, query, categories) => {
            currentResults = results;
            activeIndex = -1;
            optionSequence += 1;
            dropdown.replaceChildren();
            if (!results.length) {
              const emptyState = document.createElement("div");
              emptyState.className = "global-search-empty";
              emptyState.textContent = "No matching patients or cases.";
              dropdown.appendChild(emptyState);
              appendResultsPageActions(query, categories);
              openResults();
              announce("No matching patients or cases.");
              return;
            }

            results.forEach((result, index) => {
              const row = document.createElement("button");
              row.type = "button";
              row.className = "global-search-item";
              row.dataset.index = String(index);
              row.id = `global-search-option-${optionSequence}-${index}`;
              row.setAttribute("role", "option");
              row.setAttribute("aria-selected", "false");
              row.tabIndex = -1;

              const summary = document.createElement("div");
              summary.className = "small fw-semibold";
              const summaryParts = [
                result?.name,
                result?.age,
                result?.village,
                result?.diagnosis,
                result?.phone_number || "-",
                result?.mtno,
                result?.uhid,
              ];
              summary.textContent = summaryParts.map((value) => `${value ?? "-"}`).join(", ");
              row.appendChild(summary);

              const tags = document.createElement("div");
              tags.className = "global-search-tags";
              const resultTags = Array.isArray(result?.tags) ? result.tags : [];
              resultTags.forEach((tag) => {
                const tagChip = document.createElement("span");
                tagChip.className = "global-search-tag";
                if (tag?.bg_color && tag?.text_color) {
                  tagChip.style.backgroundColor = tag.bg_color;
                  tagChip.style.color = tag.text_color;
                  tagChip.style.borderColor = tag.border_color || tag.text_color;
                }
                const icon = typeof tag?.icon === "string" ? tag.icon : "";
                const label = typeof tag?.label === "string" ? tag.label : "";
                const kind = typeof tag?.kind === "string" ? tag.kind : "";
                const value = typeof tag?.value === "string" ? tag.value : "";
                tagChip.textContent = `${icon}${label}`;
                if (kind) {
                  tagChip.dataset.tagKind = kind;
                }
                if (kind === "category") {
                  tagChip.dataset.tagValue = value || normalizeCategoryValue(label);
                } else if (kind === "gender") {
                  tagChip.dataset.tagValue = value || "other";
                }
                tags.appendChild(tagChip);
              });
              row.appendChild(tags);
              dropdown.appendChild(row);
            });
            appendResultsPageActions(query, categories);
            openResults();
            announce(`${results.length} matching result${results.length === 1 ? "" : "s"} available.`);
          };

          const performSearch = async (generation, query, categories) => {
            if (generation !== requestGeneration || input.value.trim() !== query) {
              return;
            }
            const params = new URLSearchParams({ q: query });
            categories.forEach((category) => params.append("category", category));
            const controller = new AbortController();
            activeSearchController = controller;
            input.setAttribute("aria-busy", "true");
            dropdown.setAttribute("aria-busy", "true");
            announce("Searching patients and cases.");

            try {
              const response = await fetch(`${config.searchUrl}?${params.toString()}`, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                signal: controller.signal,
              });
              if (!response.ok) {
                throw new Error("Search request failed.");
              }
              const payload = await response.json();
              if (generation !== requestGeneration || input.value.trim() !== query) {
                return;
              }
              let results = payload.results || [];
              if (!categories.length) {
                results = results.filter((result) => (
                  Array.isArray(result?.tags)
                  && result.tags.some((tag) => tag?.kind === "record_type" && tag?.label === "Patient")
                ));
              }
              renderResults(results, query, categories);
            } catch (error) {
              if (error?.name === "AbortError") {
                return;
              }
              if (generation === requestGeneration && input.value.trim() === query) {
                closeResults();
                announce("Search is unavailable. Try again.");
              }
            } finally {
              if (generation === requestGeneration) {
                input.removeAttribute("aria-busy");
                dropdown.removeAttribute("aria-busy");
                if (activeSearchController === controller) {
                  activeSearchController = null;
                }
              }
            }
          };

          let timer = null;
          const debouncedSearch = () => {
            clearTimeout(timer);
            requestGeneration += 1;
            activeSearchController?.abort();
            activeSearchController = null;
            input.removeAttribute("aria-busy");
            dropdown.removeAttribute("aria-busy");
            closeResults();

            const generation = requestGeneration;
            const query = input.value.trim();
            const categories = selectedCategories();
            if (query.length < 2) {
              announce("");
              return;
            }
            timer = setTimeout(() => {
              performSearch(generation, query, categories);
            }, 180);
          };

          const cancelSearch = () => {
            clearTimeout(timer);
            requestGeneration += 1;
            activeSearchController?.abort();
            activeSearchController = null;
            input.removeAttribute("aria-busy");
            dropdown.removeAttribute("aria-busy");
            closeResults();
            announce("");
          };

          input.addEventListener("input", () => {
            syncPatientsLink();
            debouncedSearch();
          });

          dropdown.addEventListener("click", (event) => {
            activateOption(event.target.closest('[role="option"]'));
          });

          input.addEventListener("keydown", (event) => {
            const query = input.value.trim();
            const categories = selectedCategories();
            if (event.key === "Enter") {
              const activeOption = availableOptions()[activeIndex];
              if (activeOption) {
                event.preventDefault();
                activateOption(activeOption);
                return;
              }
              if (query.length >= 2) {
                event.preventDefault();
                window.location.assign(buildPatientResultsUrl(query));
              }
              return;
            }
            if (event.key === "Escape") {
              setFilterOpen(false);
              cancelSearch();
              return;
            }
            const options = availableOptions();
            if (dropdown.hidden || !options.length) {
              return;
            }
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveOption(Math.min(activeIndex + 1, options.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveOption(activeIndex <= 0 ? options.length - 1 : activeIndex - 1);
            } else {
              return;
            }
          });

          if (searchField) {
            searchField.addEventListener("click", (event) => {
              if (event.target.closest("[data-search-category-toggle], [data-remove-category]")) {
                return;
              }
              input.focus();
            });
          }

          input.addEventListener("focus", () => {
            searchField?.classList.add("is-focused");
            syncSearchFieldState();
          });

          input.addEventListener("blur", () => {
            window.setTimeout(() => {
              if (!container.contains(document.activeElement)) {
                searchField?.classList.remove("is-focused");
                syncSearchFieldState();
              }
            }, 0);
          });

          filterToggle?.addEventListener("click", (event) => {
            event.stopPropagation();
            setFilterOpen(!filterOpen);
          });

          categoryButtons.forEach((button) => {
            setFilterButtonState(button, true);
            button.addEventListener("click", () => {
              setFilterButtonState(button, !isButtonSelected(button));
              renderFilterButtons();
              renderSelectedTags();
              syncPatientsLink();
              syncCasesLink();
              updateFilterToggle();
              debouncedSearch();
            });
          });

          tagsContainer?.addEventListener("click", (event) => {
            const removeButton = event.target.closest("[data-remove-category]");
            if (!removeButton) {
              return;
            }
            const value = removeButton.dataset.removeCategory;
            const source = categoryButtons.find((button) => button.dataset.searchCategoryOption === value);
            if (!source) {
              return;
            }
            setFilterButtonState(source, false);
            renderFilterButtons();
            renderSelectedTags();
            syncPatientsLink();
            syncCasesLink();
            updateFilterToggle();
            debouncedSearch();
          });

          document.addEventListener("click", (event) => {
            if (!container.contains(event.target)) {
              setFilterOpen(false);
              cancelSearch();
              searchField?.classList.remove("is-focused");
            }
          });

          renderFilterButtons();
          renderSelectedTags();
          syncPatientsLink();
          syncCasesLink();
          updateFilterToggle();
        })();
