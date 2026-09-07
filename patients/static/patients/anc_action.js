(() => {
  const action = document.getElementById('id_action');
  if (!action) return;
  const update = () => {
    const correction = action.value === 'correct_edd';
    document.querySelectorAll('[data-anc-field]').forEach((row) => {
      const field = row.dataset.ancField;
      const outcomeOnly = ['outcome', 'outcome_date', 'referral_destination', 'continue_follow_up', 'cancel_task_ids'].includes(field);
      row.hidden = (correction && outcomeOnly) || (!correction && field === 'usg_edd');
    });
    if (correction) {
      document.getElementById('id_task_policy').value = 'retain';
      document.querySelectorAll('[name="cancel_task_ids"]').forEach((input) => { input.checked = false; });
    }
  };
  action.addEventListener('change', update);
  update();
})();
