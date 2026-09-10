// Управление темой. Вынесено в глобальный объект LibraryTheme,
// чтобы панель настроек читалки пользовалась той же логикой, а не дублировала её.
window.LibraryTheme = (function () {
  // Три ЯВНЫХ режима. 'system' остаётся стартовым (уважаем настройку ОС),
  // но по кнопке пользователь всегда получает предсказуемые три вида.
  const CYCLE = ['light', 'sepia', 'dark'];
  const ICONS = { light: '☀', dark: '☾', sepia: '◑', system: '◐' };
  const root = document.documentElement;

  function get() {
    try {
      return localStorage.getItem('theme') || 'system';
    } catch (e) {
      return 'system';
    }
  }

  function set(mode) {
    if (mode === 'system') {
      root.removeAttribute('data-theme');   // без атрибута работает @media prefers-color-scheme
      try { localStorage.removeItem('theme'); } catch (e) {}
    } else {
      root.setAttribute('data-theme', mode);
      try { localStorage.setItem('theme', mode); } catch (e) {}
    }
    document.querySelectorAll('[data-theme-icon]').forEach(function (node) {
      node.textContent = ICONS[mode] || ICONS.system;
    });
    document.dispatchEvent(new CustomEvent('themechange', { detail: mode }));
  }

  set(get());

  document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      const index = CYCLE.indexOf(get());
      set(CYCLE[(index + 1) % CYCLE.length]);
    });
  });

  return { get: get, set: set };
})();
