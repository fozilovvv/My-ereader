// Единый источник правды о выделенном тексте.
//
// Раньше эта логика жила внутри ai-assist.js. Теперь выделение нужно двум
// функциям — AI-подсказкам и цитатам, — поэтому она вынесена сюда: панель
// и разбор выделения описаны один раз, а потребители только подписываются.
window.ReaderSelection = (function () {
  const toolbar = document.querySelector('[data-selection-toolbar]');
  const article = document.querySelector('.chapter-content');
  if (!toolbar || !article) return { get: function () { return null; }, hide: function () {} };

  const MAX_LENGTH = 2000;
  let current = null;

  // Какая доля главы прокручена — нужна, чтобы вернуться к цитате.
  function scrollRatio() {
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;
    if (max <= 0) return 1;
    return Math.min(1, Math.max(0, window.scrollY / max));
  }

  function read() {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return null;

    const text = selection.toString().trim();
    if (!text || text.length > MAX_LENGTH) return null;

    const range = selection.getRangeAt(0);
    // Выделение должно быть внутри текста главы, а не в панели или меню.
    if (!article.contains(range.commonAncestorContainer)) return null;

    // Контекст — абзац, в котором сделано выделение: с ним AI отвечает точнее.
    const node = range.startContainer;
    const block = (node.nodeType === 1 ? node : node.parentElement)
      .closest('p, li, blockquote, h1, h2, h3');

    return {
      text: text,
      context: block ? block.textContent.trim() : '',
      ratio: scrollRatio(),
      rect: range.getBoundingClientRect(),
    };
  }

  function hide() {
    toolbar.hidden = true;
  }

  function show() {
    const found = read();
    if (!found) {
      hide();
      return;
    }
    current = found;
    toolbar.hidden = false;

    // Панель не должна вылезать за края экрана.
    const width = toolbar.offsetWidth;
    const left = found.rect.left + found.rect.width / 2 - width / 2;
    toolbar.style.left = Math.max(10, Math.min(left, window.innerWidth - width - 10)) + 'px';

    const top = found.rect.top - toolbar.offsetHeight - 10;
    toolbar.style.top = (top < 62 ? found.rect.bottom + 10 : top) + 'px';
  }

  document.addEventListener('mouseup', function (event) {
    if (event.target.closest('[data-selection-toolbar]')) return;
    setTimeout(show, 10);            // ждём, пока браузер обновит выделение
  });

  document.addEventListener('touchend', function () { setTimeout(show, 10); });
  window.addEventListener('scroll', hide, { passive: true });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') hide();
  });

  return {
    get: function () { return current; },
    hide: hide,
  };
})();
