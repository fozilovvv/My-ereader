// Каталог: переключатель вида и быстрые действия на карточках.
(function () {
  const KEY = 'catalog-view';

  // --- Вид: сетка или список -------------------------------------------

  // Только основная сетка. Полка «Продолжить чтение» на телефоне —
  // горизонтальная лента, и превращать её в список незачем: это другой
  // по смыслу блок, а не часть каталога.
  const grids = document.querySelectorAll('.book-grid[data-books]');
  const switches = document.querySelectorAll('[data-view]');

  function applyView(view) {
    grids.forEach(function (grid) { grid.classList.toggle('as-list', view === 'list'); });
    switches.forEach(function (button) {
      button.classList.toggle('active', button.dataset.view === view);
    });
    try { localStorage.setItem(KEY, view); } catch (e) {}
  }

  let saved = 'grid';
  try { saved = localStorage.getItem(KEY) || 'grid'; } catch (e) {}
  applyView(saved);

  switches.forEach(function (button) {
    button.addEventListener('click', function () { applyView(button.dataset.view); });
  });

  // --- Быстрые действия: избранное и статусы ----------------------------

  const config = document.querySelector('[data-shelf-config]');
  if (!config) return;                       // гость — кнопок на карточках нет

  const tokenInput = config.querySelector('input[name="csrfmiddlewaretoken"]');
  const token = tokenInput ? tokenInput.value : '';

  document.addEventListener('click', function (event) {
    const button = event.target.closest('[data-shelf]');
    if (!button) return;

    event.preventDefault();
    const card = button.closest('[data-book]');
    if (!card) return;

    const action = button.dataset.shelf;
    const payload = { slug: card.dataset.book };

    if (action === 'favorite') {
      payload.favorite = !button.classList.contains('on');
    } else {
      payload.status = action;               // сервер сам снимет статус при повторном нажатии
    }

    button.disabled = true;
    fetch('/api/shelf/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify(payload),
    })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        // Рисуем состояние по ответу сервера, а не по своей догадке:
        // так интерфейс не разъедется с базой.
        card.querySelectorAll('[data-shelf]').forEach(function (item) {
          const name = item.dataset.shelf;
          const on = name === 'favorite' ? data.favorite : data.status === name;
          item.classList.toggle('on', Boolean(on));
        });
      })
      .catch(function () { /* сеть пропала — состояние просто не изменится */ })
      .finally(function () { button.disabled = false; });
  });
})();
