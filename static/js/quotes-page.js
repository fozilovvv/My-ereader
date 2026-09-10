// Страница «Мои цитаты»: правка заметок и удаление.
(function () {
  const config = document.querySelector('[data-quotes-page]');
  if (!config) return;

  const tokenInput = config.querySelector('input[name="csrfmiddlewaretoken"]');
  const token = tokenInput ? tokenInput.value : '';

  function send(id, payload) {
    return fetch('/api/quotes/' + id + '/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify(payload),
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.error || 'Ошибка ' + response.status);
        return data;
      });
    });
  }

  document.addEventListener('click', function (event) {
    const card = event.target.closest('[data-quote]');
    if (!card) return;

    const id = card.dataset.quote;
    const view = card.querySelector('[data-note-view]');
    const editor = card.querySelector('[data-note-editor]');
    const toggle = card.querySelector('[data-note-toggle]');
    const save = card.querySelector('[data-note-save]');

    // --- открыть редактор заметки ---
    if (event.target.closest('[data-note-toggle]')) {
      const editing = !editor.hidden;
      editor.hidden = editing;
      save.hidden = editing;
      view.hidden = editing ? !editor.value.trim() : true;
      toggle.textContent = editing ? (editor.value.trim() ? 'Изменить заметку' : 'Заметка') : 'Отмена';
      if (!editing) editor.focus();
      return;
    }

    // --- сохранить заметку ---
    if (event.target.closest('[data-note-save]')) {
      save.disabled = true;
      send(id, { note: editor.value })
        .then(function (data) {
          view.textContent = data.note;
          view.hidden = !data.note;
          editor.hidden = true;
          save.hidden = true;
          toggle.textContent = data.note ? 'Изменить заметку' : 'Заметка';
        })
        .catch(function (error) { alert(error.message); })
        .finally(function () { save.disabled = false; });
      return;
    }

    // --- удалить цитату ---
    if (event.target.closest('[data-quote-delete]')) {
      if (!confirm('Удалить эту цитату?')) return;
      send(id, { delete: true })
        .then(function () {
          const group = card.closest('.quote-group');
          card.remove();
          // Опустела группа книги — убираем и её заголовок.
          if (group && !group.querySelector('[data-quote]')) group.remove();
        })
        .catch(function (error) { alert(error.message); });
    }
  });

  // Ctrl+Enter сохраняет заметку — привычное сочетание в текстовых полях.
  document.addEventListener('keydown', function (event) {
    if (!(event.ctrlKey || event.metaKey) || event.key !== 'Enter') return;
    const editor = event.target.closest('[data-note-editor]');
    if (!editor) return;
    const save = editor.closest('[data-quote]').querySelector('[data-note-save]');
    if (save) save.click();
  });
})();
