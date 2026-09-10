// Цитаты: сохранение выделенного фрагмента и подсветка сохранённого в тексте.
(function () {
  const config = document.querySelector('[data-quotes]');
  if (!config) return;                       // гость — цитаты недоступны

  const createUrl = config.dataset.createUrl;
  const slug = config.dataset.slug;
  const order = Number(config.dataset.order);
  const tokenInput = config.querySelector('input[name="csrfmiddlewaretoken"]');
  const token = tokenInput ? tokenInput.value : '';

  const article = document.querySelector('.chapter-content');

  // --- уведомление ------------------------------------------------------

  let toastTimer = null;

  function toast(message, isError) {
    let node = document.querySelector('.toast');
    if (!node) {
      node = document.createElement('div');
      node.className = 'toast';
      document.body.appendChild(node);
    }
    node.textContent = message;
    node.classList.toggle('error', Boolean(isError));
    node.classList.add('show');

    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { node.classList.remove('show'); }, 2600);
  }

  // --- подсветка сохранённых цитат ---------------------------------------

  // Ищем текст цитаты среди текстовых узлов главы и оборачиваем найденное
  // в <mark>. Работаем только с узлами: так разметка абзаца не ломается.
  function highlight(text) {
    if (!article || !text) return false;

    const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.parentElement.closest('mark')) continue;   // уже подсвечено
      const at = node.nodeValue.indexOf(text);
      if (at === -1) continue;

      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, at + text.length);

      const mark = document.createElement('mark');
      mark.className = 'quote-mark';
      range.surroundContents(mark);
      return true;
    }
    return false;
  }

  const saved = document.getElementById('chapter-quotes');
  if (saved) {
    let stored = [];
    try { stored = JSON.parse(saved.textContent) || []; } catch (e) { stored = []; }
    // От длинных к коротким: иначе короткая цитата может «съесть» кусок длинной.
    stored
      .slice()
      .sort(function (a, b) { return b.text.length - a.text.length; })
      .forEach(function (quote) { highlight(quote.text); });
  }

  // --- сохранение -------------------------------------------------------

  document.querySelectorAll('[data-quote-save]').forEach(function (button) {
    button.addEventListener('click', function () {
      const selection = window.ReaderSelection.get();
      if (!selection) return;

      const text = selection.text;
      window.ReaderSelection.hide();
      button.disabled = true;

      fetch(createUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({
          slug: slug,
          order: order,
          text: text,
          scroll_ratio: selection.ratio,
        }),
      })
        .then(function (response) {
          return response.json().then(function (data) {
            if (!response.ok) throw new Error(data.error || 'Ошибка ' + response.status);
            return data;
          });
        })
        .then(function () {
          highlight(text);
          window.getSelection().removeAllRanges();
          toast('Цитата сохранена');
        })
        .catch(function (error) { toast(error.message, true); })
        .finally(function () { button.disabled = false; });
    });
  });
})();
