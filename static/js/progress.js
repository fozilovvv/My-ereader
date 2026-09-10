// Сохранение прогресса чтения: отслеживаем прокрутку и шлём её на сервер.
(function () {
  const node = document.querySelector('[data-progress]');
  if (!node) return;                       // гость — сохранять некуда

  const url = node.dataset.url;
  const slug = node.dataset.slug;
  const order = parseInt(node.dataset.order, 10);
  const restore = parseFloat(node.dataset.restore || '0');
  const tokenInput = node.querySelector('input[name="csrfmiddlewaretoken"]');
  const token = tokenInput ? tokenInput.value : '';

  const SAVE_EVERY_MS = 3000;              // не чаще одного запроса в 3 секунды
  const MIN_CHANGE = 0.01;                 // и только если сдвинулись заметно

  let lastSent = -1;
  let timer = null;

  // Какая доля главы прокручена: 0 — начало, 1 — конец.
  function ratio() {
    const doc = document.documentElement;
    const max = doc.scrollHeight - window.innerHeight;

    // Глава целиком помещается на экран — прокручивать нечего,
    // значит текст уже перед глазами и глава пройдена.
    if (max <= 0) return 1;

    // У самого низа добиваем до единицы: иначе из-за округлений
    // дочитанная книга навсегда застревала бы на 99%.
    if (window.scrollY + window.innerHeight >= doc.scrollHeight - 24) return 1;

    return Math.min(1, Math.max(0, window.scrollY / max));
  }

  function send(value, useKeepalive) {
    lastSent = value;
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ slug: slug, order: order, scroll_ratio: value }),
      // keepalive: браузер доотправит запрос, даже если вкладку уже закрыли
      keepalive: Boolean(useKeepalive),
    }).catch(function () { /* сеть пропала — не мешаем человеку читать */ });
  }

  function scheduleSave() {
    if (timer) return;                     // запрос уже запланирован
    timer = setTimeout(function () {
      timer = null;
      const value = ratio();
      if (Math.abs(value - lastSent) >= MIN_CHANGE) send(value, false);
    }, SAVE_EVERY_MS);
  }

  window.addEventListener('scroll', scheduleSave, { passive: true });

  // Уход со страницы — последний шанс сохранить точную позицию.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') send(ratio(), true);
  });
  window.addEventListener('pagehide', function () { send(ratio(), true); });

  // Возвращаем читателя туда, где он остановился, и сразу фиксируем позицию.
  // requestAnimationFrame — ждём, пока браузер разложит текст: до этого
  // scrollHeight ещё не окончательный, и расчёт был бы неверным.
  requestAnimationFrame(function () {
    if (restore > 0) {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (max > 0) window.scrollTo(0, max * restore);
    }
    send(ratio(), false);
  });
})();
