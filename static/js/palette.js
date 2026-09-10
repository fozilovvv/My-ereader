// Палитра поиска: Ctrl + K на любой странице.
(function () {
  const overlay = document.querySelector('[data-palette]');
  if (!overlay) return;

  const input = overlay.querySelector('[data-palette-input]');
  const results = overlay.querySelector('[data-palette-results]');

  const DEBOUNCE_MS = 180;      // ждём паузу в наборе, чтобы не слать запрос на каждую букву
  let timer = null;
  let items = [];               // текущие результаты
  let cursor = -1;              // подсвеченная строка
  let lastQuery = '';

  // --- открытие и закрытие ---------------------------------------------

  function open(initial) {
    overlay.hidden = false;
    document.body.style.overflow = 'hidden';    // фон не прокручивается
    input.value = initial || '';
    input.focus();
    input.select();
    schedule();
  }

  function close() {
    overlay.hidden = true;
    document.body.style.overflow = '';
    results.innerHTML = '';
    items = [];
    cursor = -1;
    lastQuery = '';
  }

  document.addEventListener('keydown', function (event) {
    const combo = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
    if (combo) {
      event.preventDefault();
      overlay.hidden ? open('') : close();
      return;
    }
    if (event.key === 'Escape' && !overlay.hidden) close();
  });

  // Поле в шапке больше не форма для ввода, а кнопка вызова палитры.
  document.querySelectorAll('[data-palette-open]').forEach(function (field) {
    field.addEventListener('focus', function (event) {
      event.target.blur();
      open(event.target.value);
    });
  });

  overlay.addEventListener('mousedown', function (event) {
    if (event.target === overlay) close();      // клик по затемнению
  });

  // --- запрос к серверу --------------------------------------------------

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(run, DEBOUNCE_MS);
  }

  function run() {
    const query = input.value.trim();
    if (query === lastQuery) return;
    lastQuery = query;

    if (query.length < 2) {
      render([], query);
      return;
    }

    showSkeleton();
    fetch('/api/search/?q=' + encodeURIComponent(query))
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (input.value.trim() === query) render(data.books, query);
      })
      .catch(function () { render([], query); });
  }

  input.addEventListener('input', schedule);

  // --- вывод результатов -------------------------------------------------

  // Пока летит запрос, показываем «скелет» строк, а не пустоту:
  // так окно не мигает и чувствуется быстрее, чем оно есть.
  function showSkeleton() {
    var row =
      '<div class="skeleton-row">' +
        '<div class="skeleton-box thumb"></div>' +
        '<div class="skeleton-lines">' +
          '<div class="skeleton-box line"></div>' +
          '<div class="skeleton-box line short"></div>' +
        '</div>' +
      '</div>';
    results.innerHTML = '<div class="palette-skeleton">' + row + row + row + '</div>';
  }

  function escapeHtml(text) {
    const node = document.createElement('div');
    node.textContent = text == null ? '' : text;
    return node.innerHTML;
  }

  function render(books, query) {
    items = books || [];
    cursor = items.length ? 0 : -1;

    if (!items.length) {
      results.innerHTML = query.length < 2
        ? '<div class="palette-empty">Введите хотя бы две буквы</div>'
        : '<div class="palette-empty">Ничего не нашлось. Enter — искать в каталоге</div>';
      return;
    }

    results.innerHTML = items.map(function (book, index) {
      const thumb = book.cover
        ? '<img src="' + escapeHtml(book.cover) + '" alt="">'
        : '<span>' + escapeHtml(book.letter) + '</span>';

      return '<a class="palette-item' + (index === 0 ? ' active' : '') + '"' +
             ' href="' + escapeHtml(book.url) + '" data-index="' + index + '">' +
             '<span class="palette-thumb" style="--hue: ' + Number(book.hue) + '">' + thumb + '</span>' +
             '<span class="palette-text">' +
               '<span class="pt-title">' + escapeHtml(book.title) + '</span>' +
               '<span class="pt-author">' + escapeHtml(book.author) + '</span>' +
             '</span>' +
             '<span class="palette-time">' + escapeHtml(book.time) + '</span>' +
             '</a>';
    }).join('');
  }

  function move(step) {
    if (!items.length) return;
    cursor = (cursor + step + items.length) % items.length;
    const nodes = results.querySelectorAll('.palette-item');
    nodes.forEach(function (node, index) {
      node.classList.toggle('active', index === cursor);
    });
    if (nodes[cursor]) nodes[cursor].scrollIntoView({ block: 'nearest' });
  }

  input.addEventListener('keydown', function (event) {
    if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
    else if (event.key === 'Enter') {
      event.preventDefault();
      if (cursor >= 0 && items[cursor]) {
        window.location.href = items[cursor].url;
      } else if (input.value.trim()) {
        // Ничего не выбрано — уводим на обычную страницу каталога с поиском.
        window.location.href = '/?q=' + encodeURIComponent(input.value.trim());
      }
    }
  });

  results.addEventListener('mousemove', function (event) {
    const item = event.target.closest('.palette-item');
    if (!item) return;
    cursor = Number(item.dataset.index);
    results.querySelectorAll('.palette-item').forEach(function (node, index) {
      node.classList.toggle('active', index === cursor);
    });
  });
})();
