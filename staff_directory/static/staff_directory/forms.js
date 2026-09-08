const button = document.getElementById("add-phone");
const total = document.getElementById("id_phones-TOTAL_FORMS");
const template = document.getElementById("phone-empty");
button?.addEventListener("click", () => {
  const index = Number(total.value);
  if (index >= 10) return;
  const holder = document.createElement("div");
  holder.innerHTML = template.innerHTML.replaceAll("__prefix__", String(index));
  document.getElementById("phone-rows").append(...holder.children);
  total.value = String(index + 1);
  button.disabled = index + 1 >= 10;
});
if (button) button.disabled = Number(total.value) >= 10;
