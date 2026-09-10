// Панель настроек чтения. Всё хранится в localStorage браузера —
// серверу об этом знать незачем, а применяется мгновенно, без перезагрузки.
(function () {
  const KEY = 'reader-settings';
  const DEFAULTS = { size: 19, height: 1.75, width: 34, font: 'serif' };
  const FONTS = {
    serif: "Georgia, 'Times New Roman', serif",
    sans: "'Segoe UI', system-ui, -apple-system, sans-serif",
  };
  const UNITS = { size: 'px', height: '', width: 'rem' };

  const root = document.documentElement;
  const panel = document.querySelector('[data-settings]');
  if (!panel) return;

  let state = load();

  function load() {
    try {
      return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem(KEY) || '{}'));
    } catch (e) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }

  // Настройки — это просто CSS-переменные. Меняем их на <html>,
  // и вся вёрстка перестраивается сама: ни одного пересчёта руками.
  function apply() {
    root.style.setProperty('--reading-size', state.size + 'px');
    root.style.setProperty('--reading-height', String(state.height));
    root.style.setProperty('--reading-width', state.width + 'rem');
    root.style.setProperty('--font-book', FONTS[state.font] || FONTS.serif);
    syncControls();
  }

  function syncControls() {
    panel.querySelectorAll('[data-range]').forEach(function (input) {
      const name = input.dataset.range;
      input.value = state[name];
      const readout = panel.querySelector('[data-readout="' + name + '"]');
      if (readout) readout.textContent = state[name] + UNITS[name];
    });

    panel.querySelectorAll('[data-group]').forEach(function (group) {
      const name = group.dataset.group;
      const active = name === 'theme' ? window.LibraryTheme.get() : state[name];
      group.querySelectorAll('button').forEach(function (button) {
        button.classList.toggle('active', button.dataset.value === active);
      });
    });
  }

  // --- обработчики ---------------------------------------------------

  panel.querySelectorAll('[data-range]').forEach(function (input) {
    input.addEventListener('input', function () {
      state[input.dataset.range] = parseFloat(input.value);
      apply();
      save();
    });
  });

  panel.querySelectorAll('[data-group] button').forEach(function (button) {
    button.addEventListener('click', function () {
      const name = button.closest('[data-group]').dataset.group;
      if (name === 'theme') {
        window.LibraryTheme.set(button.dataset.value);
      } else {
        state[name] = button.dataset.value;
        save();
      }
      apply();
    });
  });

  const resetButton = panel.querySelector('[data-settings-reset]');
  if (resetButton) {
    resetButton.addEventListener('click', function () {
      state = Object.assign({}, DEFAULTS);   // тему не трогаем: это отдельный выбор
      apply();
      save();
    });
  }

  document.addEventListener('themechange', syncControls);

  // --- открытие / закрытие -------------------------------------------

  document.querySelectorAll('[data-settings-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) syncControls();
    });
  });

  document.addEventListener('click', function (event) {
    if (panel.hidden) return;
    if (panel.contains(event.target) || event.target.closest('[data-settings-toggle]')) return;
    panel.hidden = true;
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') panel.hidden = true;
  });

  apply();
})();
