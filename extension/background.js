const URL_BACKEND = 'http://localhost:5000/webhook';

// Таймаут на сетевой запрос. Если десктоп-приложение запущено, но worker завис
// или сокет принял соединение и не отвечает, без таймаута fetch висел бы вечно,
// а бейдж "..." остался бы навсегда. 8 секунд — с запасом для локального сервера.
const FETCH_TIMEOUT_MS = 8000;

// Защита от гонки бейджа: бейдж в Chrome глобальный для всего расширения, поэтому
// при быстрых кликах по разным вкладкам setTimeout от раннего запроса мог затереть
// индикатор позднего. Каждый клик получает уникальный токен; сброс/обновление
// бейджа выполняется только если токен всё ещё актуален (т.е. это последний клик).
let badgeToken = 0;

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}

// Очищает бейдж через задержку, но только если с момента запуска не было нового клика.
function clearBadgeLater(token, delay = 2500) {
  setTimeout(() => {
    if (token === badgeToken) {
      chrome.action.setBadgeText({ text: '' });
    }
  }, delay);
}

// Применяет финальный бейдж только если этот клик всё ещё последний.
function applyFinalBadge(token, text, color) {
  if (token !== badgeToken) {
    return; // Появился более новый клик — не вмешиваемся в его индикацию.
  }
  setBadge(text, color);
  clearBadgeLater(token);
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

chrome.action.onClicked.addListener(async (tab) => {
  // Текущему клику присваиваем новый токен и становимся "последним" кликом.
  const token = ++badgeToken;

  // Оранжевый индикатор загрузки.
  setBadge('...', '#FFA500');

  try {
    if (!tab || !tab.id || !tab.url || !tab.url.startsWith('http')) {
      throw new Error('Парсинг невозможен на этой вкладке');
    }

    // Вытаскиваем текст со страницы.
    const injection = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.body.innerText
    });
    const pageText = (injection && injection[0] && injection[0].result) || '';

    // Отправляем данные в Job Hunter AI с таймаутом.
    let response;
    try {
      response = await fetchWithTimeout(URL_BACKEND, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: tab.url,
          title: tab.title,
          text: pageText
        })
      }, FETCH_TIMEOUT_MS);
    } catch (netErr) {
      if (netErr && netErr.name === 'AbortError') {
        throw new Error('Превышено время ожидания ответа сервера (таймаут)');
      }
      // ERR_CONNECTION_REFUSED и прочие сетевые сбои — приложение, скорее всего, выключено.
      throw new Error('Нет связи с Job Hunter AI. Запустите приложение');
    }

    if (!response.ok) {
      throw new Error(`Сервер ответил ошибкой: ${response.status}`);
    }

    // Сервер всегда отвечает JSON-ом. Важно: status="ignored" приходит с HTTP 200,
    // когда ассистент выключен, поэтому одного response.ok недостаточно —
    // нужно прочитать тело и различить реальные состояния.
    let data = {};
    try {
      data = await response.json();
    } catch (parseErr) {
      console.warn('Job Hunter AI: не удалось разобрать JSON ответа сервера:', parseErr);
      // Тело нечитаемо, но HTTP 200 — трактуем как мягкий успех.
      data = {};
    }

    if (data.status === 'ignored') {
      // Ассистент запущен, но приём вакансий выключен — вакансия НЕ обработана.
      // Жёлтый OFF, чтобы пользователь не думал, что отправка прошла.
      applyFinalBadge(token, 'OFF', '#FFC107');
    } else if (data.status === 'error') {
      // Сервер явно сообщил об ошибке обработки в теле ответа.
      throw new Error(`Сервер сообщил об ошибке: ${data.reason || 'неизвестно'}`);
    } else {
      // status === "received" (или иной успешный ответ) — вакансия принята в очередь.
      applyFinalBadge(token, 'OK', '#4CAF50');
    }

  } catch (error) {
    console.error('Ошибка парсера Job Hunter AI:', error);
    // Красный индикатор ошибки (только если этот клик всё ещё последний).
    applyFinalBadge(token, 'ERR', '#D32F2F');
  }
});
