const URL_BACKEND = 'http://localhost:5000/webhook';

// Network timeout. Without it, fetch would hang forever if the desktop app is
// running but its worker is stuck or the socket accepted the connection silently.
// 8 s is generous for a local server.
const FETCH_TIMEOUT_MS = 8000;

// Must stay in sync with manifest.json → action.default_title so the tooltip
// resets cleanly after an error.
const DEFAULT_TITLE = 'Отправить вакансию в Job Hunter AI';

// Badge race-condition guard: the Chrome action badge is global for the whole
// extension. Rapid clicks on different tabs could let a setTimeout from an
// earlier request overwrite the badge of a later one. Each click gets a unique
// token; badge updates are skipped unless the token is still current.
let badgeToken = 0;

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) {
    chrome.action.setBadgeBackgroundColor({ color });
  }
}

// Clears the badge after a delay, but only if no newer click has started.
function clearBadgeLater(token, delay = 2500) {
  setTimeout(() => {
    if (token === badgeToken) {
      chrome.action.setBadgeText({ text: '' });
    }
  }, delay);
}

// Applies the final badge + tooltip only if this click is still the latest one.
// title defaults to DEFAULT_TITLE so success callers need no extra argument.
function applyFinalBadge(token, text, color, title = DEFAULT_TITLE) {
  if (token !== badgeToken) {
    return; // A newer click is already in progress — don't interfere.
  }
  setBadge(text, color);
  chrome.action.setTitle({ title });
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
  // This click becomes the current one; earlier badge timers will no-op.
  const token = ++badgeToken;

  // Orange spinner badge while the request is in flight.
  setBadge('...', '#FFA500');

  // Reset any stale error tooltip from a previous failed run before we start.
  chrome.action.setTitle({ title: DEFAULT_TITLE });

  try {
    // With activeTab alone, Chrome can strip tab.url when the tab was opened in
    // the background or when the icon is clicked before the navigation commits.
    // The "tabs" permission in manifest.json prevents that stripping.
    if (!tab?.id || !tab.url?.startsWith('http')) {
      throw new Error('Парсинг невозможен на этой вкладке');
    }

    // Extract the page text via content script injection.
    const injection = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.body.innerText
    });
    // Truncate to 50 000 chars: enough for any AI model to analyse a job posting,
    // prevents sending multi-MB pages that would stall Flask's JSON parser under GIL.
    const pageText = (injection?.[0]?.result ?? '').slice(0, 50000);

    // SPAs (LinkedIn, Greenhouse, etc.) temporarily blank document.body.innerText
    // during client-side route transitions. Sending an empty payload would silently
    // enqueue a useless record in the backend without any useful text to analyse.
    if (!pageText.trim()) {
      throw new Error(
        'Текст страницы пуст — страница ещё отрисовывается. Дождитесь загрузки и попробуйте снова'
      );
    }

    // Send the vacancy data to the local Job Hunter AI desktop app.
    let response;
    try {
      response = await fetchWithTimeout(URL_BACKEND, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: tab.url, title: tab.title, text: pageText })
      }, FETCH_TIMEOUT_MS);
    } catch (netErr) {
      if (netErr?.name === 'AbortError') {
        throw new Error('Превышено время ожидания ответа сервера (таймаут)');
      }
      // ERR_CONNECTION_REFUSED and similar network failures mean the app is likely off.
      throw new Error('Нет связи с Job Hunter AI. Запустите приложение');
    }

    if (!response.ok) {
      throw new Error(`Сервер ответил ошибкой: ${response.status}`);
    }

    // The server always responds with JSON. Important: status="ignored" arrives
    // with HTTP 200 when the assistant is disabled, so response.ok alone is not
    // enough — we must read the body to distinguish real outcomes.
    let data = {};
    try {
      data = await response.json();
    } catch (parseErr) {
      // Unreadable body with HTTP 200 — treat as a soft success.
      console.warn('Job Hunter AI: failed to parse server JSON response:', parseErr);
      data = {};
    }

    if (data.status === 'ignored') {
      // App is running but intake is disabled — the vacancy was NOT processed.
      // Yellow OFF badge so the user knows the submission did not go through.
      applyFinalBadge(token, 'OFF', '#FFC107');
    } else if (data.status === 'error') {
      // Server explicitly reported a processing error in the response body.
      throw new Error(`Сервер сообщил об ошибке: ${data.reason ?? 'неизвестно'}`);
    } else {
      // status === "received" (or any other success) — vacancy accepted into queue.
      applyFinalBadge(token, 'OK', '#4CAF50');
    }

  } catch (error) {
    console.error('Job Hunter AI parser error:', error);
    // Surface the human-readable message as a hover tooltip so the user knows
    // what went wrong without opening DevTools. Resets automatically on the next click.
    applyFinalBadge(token, 'ERR', '#D32F2F', error.message ?? 'Неизвестная ошибка');
  }
});
