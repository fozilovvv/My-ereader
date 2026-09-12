// Выдвижная панель («off-canvas») для узких экранов.
//
// Главная мысль: никакой второй разметки. Сайдбар и меню шапки — это те же
// самые узлы страницы, скрипт лишь переносит их в панель, когда экран узкий,
// и возвращает на место, когда широкий. Копия меню «только для телефона»
// рано или поздно расходится с оригиналом — здесь расходиться нечему.
(function () {
  // Тот же рубеж, что и в CSS. iPad Air (820) и mini (768) получают панель,
  // iPad Pro (1024) — нет: ему хватает ширины на боковую колонку.
  const BREAKPOINT = 900;

  const drawer = document.querySelector('[data-drawer]');
  const panelBody = document.querySelector('[data-drawer-body]');
  const toggle = document.querySelector('[data-nav-toggle]');
  if (!drawer || !panelBody || !toggle) return;

  // Запоминаем, откуда взят каждый блок: parent + следующий сосед. Этого
  // достаточно, чтобы вернуть узел ровно на прежнее место, даже если рядом
  // есть другие элементы.
  // Порядок важен и задан здесь явно: сначала полки и категории — за ними
  // человек и открывает панель, — и только потом язык, тема и выход.
  // querySelectorAll вернул бы их в порядке разметки, то есть наоборот.
  const movable = [];
  ['.sidebar', '[data-nav]'].forEach(function (selector) {
    const node = document.querySelector(selector);
    if (node) movable.push({ node: node, parent: node.parentNode, next: node.nextSibling });
  });

  let inDrawer = false;

  function moveIn() {
    if (inDrawer) return;
    movable.forEach(function (item) { panelBody.appendChild(item.node); });
    inDrawer = true;
  }

  function moveBack() {
    if (!inDrawer) return;
    movable.forEach(function (item) { item.parent.insertBefore(item.node, item.next); });
    inDrawer = false;
  }

  function isOpen() {
    return drawer.classList.contains('open');
  }

  function open() {
    drawer.hidden = false;
    // Панель уезжает за левый край, пока у неё нет класса open. Класс вешаем
    // на следующем кадре: иначе браузер применит оба состояния разом и
    // покажет панель без всякого движения.
    requestAnimationFrame(function () { drawer.classList.add('open'); });
    toggle.classList.add('on');
    toggle.setAttribute('aria-expanded', 'true');
    // Фиксируем страницу: без этого палец прокручивает каталог под панелью.
    document.body.classList.add('drawer-open');
    document.documentElement.classList.add('drawer-open');
  }

  function close() {
    drawer.classList.remove('open');
    toggle.classList.remove('on');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('drawer-open');
    document.documentElement.classList.remove('drawer-open');
    // Прячем только после анимации, иначе панель исчезнет рывком.
    setTimeout(function () { if (!isOpen()) drawer.hidden = true; }, 240);
  }

  function sync() {
    if (window.innerWidth <= BREAKPOINT) {
      moveIn();
    } else {
      close();
      moveBack();
    }
  }

  toggle.addEventListener('click', function () {
    if (isOpen()) close(); else open();
  });

  // Закрываем: крестик, тёмный фон, Esc, переход по ссылке внутри панели.
  drawer.addEventListener('click', function (event) {
    if (event.target === drawer ||
        event.target.closest('[data-nav-close]') ||
        event.target.closest('a')) {
      close();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && isOpen()) close();
  });

  window.addEventListener('resize', sync);
  sync();
})();
