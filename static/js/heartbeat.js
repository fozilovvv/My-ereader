// Сигнал присутствия: «вкладка открыта, человек на сайте».
//
// Длительность визита считает сервер — по разнице между сигналами. Браузер
// сообщает только факт: он не может приписать себе лишние часы, потому что
// не он решает, сколько времени зачесть.
(function () {
  const config = document.querySelector('[data-heartbeat]');
  if (!config) return;                       // гость — ничего не отправляем

  const url = config.dataset.url;
  const seconds = parseInt(config.dataset.interval, 10) || 30;
  const tokenInput = config.querySelector('input[name="csrfmiddlewaretoken"]');
  const token = tokenInput ? tokenInput.value : '';

  // Вкладка в фоне — это не время на сайте. Человек мог уйти на другой сайт,
  // а вкладку оставить открытой на неделю.
  function visible() {
    return document.visibilityState === 'visible';
  }

  function beat() {
    if (!visible()) return;

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ page: location.pathname }),
      // keepalive: запрос уходит, даже если страницу в этот момент закрывают
      keepalive: true,
    }).catch(function () { /* сеть пропала — следующий сигнал наверстает */ });
  }

  beat();                                    // первый — сразу при открытии
  setInterval(beat, seconds * 1000);

  // Вернулись на вкладку — отмечаемся, не дожидаясь конца интервала.
  document.addEventListener('visibilitychange', function () {
    if (visible()) beat();
  });
})();
