// AI-помощник: перевод, объяснение и выжимка главы.
// Работу с выделением ведёт общий модуль ReaderSelection (см. selection.js).
(function () {
  const config = document.querySelector('[data-ai]');
  if (!config) return;                       // гость — помощник недоступен

  const url = config.dataset.url;
  const slug = config.dataset.slug;
  const order = config.dataset.order;
  const tokenInput = config.querySelector('input[name="csrfmiddlewaretoken"]');
  const token = tokenInput ? tokenInput.value : '';

  const panel = document.querySelector('[data-ai-panel]');
  const panelTitle = panel.querySelector('[data-ai-title]');
  const panelBody = panel.querySelector('[data-ai-body]');

  const TITLES = {
    translate: 'Перевод',
    explain: 'Объяснение',
    summarize: 'Выжимка главы',
  };

  function escapeHtml(text) {
    const node = document.createElement('div');
    node.textContent = text == null ? '' : text;
    return node.innerHTML;
  }

  // Ответ модели — обычный текст. Экранируем его целиком, и только потом
  // разрешаем **жирный** и переносы строк. Порядок важен: сначала защита.
  function format(text) {
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');
  }

  function request(action) {
    const selection = window.ReaderSelection.get();
    if (action !== 'summarize' && !selection) return;

    window.ReaderSelection.hide();
    panel.hidden = false;
    panelTitle.textContent = TITLES[action] || 'Ответ';
    panelBody.innerHTML = '<div class="ai-loading"><span></span><span></span><span></span></div>';

    const payload = { action: action, slug: slug, order: Number(order) };
    if (action !== 'summarize') {
      payload.fragment = selection.text;
      payload.context = selection.context;
    }

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || 'Ошибка ' + response.status);
          return data;
        });
      })
      .then(function (data) { panelBody.innerHTML = format(data.answer); })
      .catch(function (error) {
        panelBody.innerHTML = '<div class="ai-error">' + escapeHtml(error.message) + '</div>';
      });
  }

  document.querySelectorAll('[data-ai-action]').forEach(function (button) {
    button.addEventListener('click', function () { request(button.dataset.aiAction); });
  });

  panel.querySelector('[data-ai-close]').addEventListener('click', function () {
    panel.hidden = true;
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') panel.hidden = true;
  });
})();
