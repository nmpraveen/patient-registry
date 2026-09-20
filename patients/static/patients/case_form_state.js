(() => {
  // A preview is a projection of one form snapshot, never an owner of newer input.
  window.medtrackCaseFormState = ({ form, previewId, identityId, fields }) => {
    const category = () => form.querySelector('[name="category"]:checked')?.value
      || form.querySelector('select[name="category"]')?.value || "";
    const fingerprint = () => JSON.stringify(Array.from(new FormData(form).entries()));
    const drafts = new Map();
    const snapshots = new WeakMap();
    const accepted = new WeakSet();
    const timers = new Map();
    let renderedCategory = category();
    const elements = (name) => Array.from(form.querySelectorAll(`[name="${CSS.escape(name)}"]`));
    const remember = () => {
      const values = new Map();
      fields.forEach((name) => {
        const inputs = elements(name);
        if (!inputs.length) return;
        values.set(name, inputs.map((input) => ({ value: input.value, checked: input.checked })));
      });
      drafts.set(renderedCategory, values);
    };
    const refresh = (id) => {
      window.clearTimeout(timers.get(id));
      timers.set(id, window.setTimeout(() => {
        const element = document.getElementById(id);
        if (element) window.htmx?.trigger(element, element.getAttribute("hx-trigger"));
      }, 220));
    };
    const isOurs = (event) => [previewId, identityId].includes(event.detail?.elt?.id);
    document.body.addEventListener("htmx:beforeRequest", (event) => {
      if (!isOurs(event)) return;
      snapshots.set(event.detail.xhr, fingerprint());
    });
    document.body.addEventListener("htmx:beforeOnLoad", (event) => {
      if (!isOurs(event)) return;
      if (snapshots.get(event.detail.xhr) !== fingerprint()) {
        event.preventDefault();
        refresh(event.detail.elt.id);
      } else {
        accepted.add(event.detail.xhr);
      }
    });
    // Capture the departing workflow before a category response replaces it.
    form.addEventListener("input", remember, true);
    form.addEventListener("change", remember, true);
    remember();
    return {
      remember,
      completed(event) {
        return event.detail?.elt?.id === previewId && event.detail.successful
          && accepted.has(event.detail.xhr);
      },
      restore() {
        const nextCategory = category();
        if (nextCategory === renderedCategory) return false;
        const saved = drafts.get(nextCategory);
        let changed = false;
        saved?.forEach((values, name) => {
          elements(name).forEach((input, index) => {
            const value = values[index];
            if (!value) return;
            if (input.type === "checkbox" || input.type === "radio") {
              changed ||= input.checked !== value.checked;
              input.checked = value.checked;
            } else {
              changed ||= input.value !== value.value;
              input.value = value.value;
            }
          });
        });
        renderedCategory = nextCategory;
        remember();
        return changed;
      },
    };
  };
})();
