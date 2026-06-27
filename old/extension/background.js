const URL_BACKEND = 'http://localhost:5000/webhook';

chrome.action.onClicked.addListener(async (tab) => {
  // Включаем оранжевый индикатор загрузки
  chrome.action.setBadgeText({ text: '...' });
  chrome.action.setBadgeBackgroundColor({ color: '#FFA500' }); 

  try {
    if (!tab || !tab.id || !tab.url || !tab.url.startsWith('http')) {
      throw new Error('Парсинг невозможен на этой вкладке');
    }

    // Вытаскиваем текст со страницы
    const [{ result: pageText }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.body.innerText
    });

    // Отправляем данные в Job Hunter AI
    const response = await fetch(URL_BACKEND, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url: tab.url,
        title: tab.title,
        text: pageText
      })
    });

    if (response.ok) {
      // Зеленый индикатор успеха
      chrome.action.setBadgeText({ text: 'OK' });
      chrome.action.setBadgeBackgroundColor({ color: '#4CAF50' });
      setTimeout(() => chrome.action.setBadgeText({ text: '' }), 2500);
    } else {
      throw new Error(`Сервер ответил ошибкой: ${response.status}`);
    }

  } catch (error) {
    console.error('Ошибка парсера Job Hunter AI:', error);
    // Красный индикатор ошибки
    chrome.action.setBadgeText({ text: 'ERR' });
    chrome.action.setBadgeBackgroundColor({ color: '#D32F2F' });
    setTimeout(() => chrome.action.setBadgeText({ text: '' }), 2500);
  }
});