// Читалка: выдвижное оглавление и навигация стрелками.
(function () {
  const drawer = document.querySelector('[data-toc]');

  document.querySelectorAll('[data-toc-toggle]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (drawer) drawer.hidden = !drawer.hidden;
    });
  });

  // Клик мимо панели — закрыть.
  document.addEventListener('click', function (event) {
    if (!drawer || drawer.hidden) return;
    if (drawer.contains(event.target) || event.target.closest('[data-toc-toggle]')) return;
    drawer.hidden = true;
  });

  // Листаем главы клавишами ← и →.
  document.addEventListener('keydown', function (event) {
    if (event.target.matches('input, textarea')) return;

    if (event.key === 'Escape' && drawer && !drawer.hidden) {
      drawer.hidden = true;
      return;
    }
    const selector = event.key === 'ArrowLeft' ? '.chapter-nav a:first-child'
                   : event.key === 'ArrowRight' ? '.chapter-nav a:last-child'
                   : null;
    if (!selector) return;

    const link = document.querySelector(selector);
    if (link && link.href) window.location.href = link.href;
  });
})();
