# jh_ai_engine.py
import json
import re
import urllib.request
import urllib.error
import socket
import time


# =====================================================================
# СТРУКТУРИРОВАННЫЕ ОШИБКИ ДВИЖКА
# Позволяют UI / системе статусов отличать тип сбоя и показывать
# пользователю понятное сообщение (сеть / таймаут / парсинг / авторизация).
# =====================================================================
class AIEngineError(Exception):
    """Базовый класс всех ошибок ИИ-движка."""
    user_message = "Произошёл сбой ИИ-движка."

    def __init__(self, message=None):
        super().__init__(message or self.user_message)
        self.detail = message or self.user_message


class AINetworkError(AIEngineError):
    """Сетевая ошибка: сервер недоступен, отказ соединения, DNS и т.п."""
    user_message = "Ошибка сети: не удалось соединиться с сервером модели."


class AILocalServerError(AINetworkError):
    """Локальный сервер (Ollama / LM Studio) не запущен или не отвечает."""
    user_message = "Локальный сервер не запущен. Проверьте Ollama / LM Studio."


class AITimeoutError(AIEngineError):
    """Таймаут ответа модели (часто у медленных локальных моделей)."""
    user_message = "Превышено время ожидания ответа модели (таймаут)."


class AIAuthError(AIEngineError):
    """Ошибка авторизации API (неверный или отсутствующий ключ)."""
    user_message = "Ошибка авторизации API. Проверьте правильность ключа."


class AIResponseParseError(AIEngineError):
    """Модель вернула некорректный / неразбираемый ответ."""
    user_message = "Модель вернула повреждённый или нечитаемый ответ."


class AIRateLimitError(AIEngineError):
    """Исчерпан лимит частоты запросов (429)."""
    user_message = "Исчерпан лимит запросов к API. Попробуйте позже."


# =====================================================================
# БЕЗОПАСНЫЕ ПАРАМЕТРЫ ГЕНЕРАЦИИ ДЛЯ ЛОКАЛЬНЫХ МОДЕЛЕЙ (guard clause)
# LM Studio / Ollama могут стартовать с некорректными дефолтами в UI
# самого сервера. Мы жёстко навязываем безопасные значения.
# =====================================================================
LOCAL_SAFE_PARAMS = {
    "temperature": 0.1,
    "top_p": 0.9,
    "max_tokens": 2048,
    "num_ctx": 8192,         # размер контекста для Ollama
    "repeat_penalty": 1.15,  # предотвращает repetition loop в 4-bit моделях
    "frequency_penalty": 0.1,  # аналог repeat_penalty для OpenAI-совместимых (LM Studio)
}

# Минимально допустимая скорость генерации (токенов/сек), чтобы уложиться
# в 60-секундный лимит очереди для типичного ответа Stage 2 (~700 токенов).
MIN_TOKENS_PER_SEC = 12
QUEUE_TIME_BUDGET_SEC = 60


def clean_and_parse_json(raw_text):
    """
    Очищает вывод LLM и парсит JSON с многоуровневым ремонтом.
    Уровни обработки (применяются последовательно до первого успеха):
      1. Прямой парсинг после удаления markdown-обёртки.
      2. Висящие запятые ,} / ,]
      3. Python True/False/None → JSON true/false/null
      4. Одинарные кавычки → двойные (только если двойных нет вообще)
      5. Смешанный режим: замена одинарных кавычек при наличии двойных
    """
    if not raw_text:
        raise AIResponseParseError("Получен пустой ответ от ИИ.")

    clean_text = raw_text.strip()

    # Убираем markdown-обёртку ```json ... ```
    if clean_text.startswith("```"):
        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
        clean_text = re.sub(r"\s*```$", "", clean_text)
    clean_text = clean_text.strip()

    # Извлекаем первый полный JSON-объект {…}
    match = re.search(r"(\{.*\})", clean_text, re.DOTALL)
    if not match:
        raise AIResponseParseError("ИИ не вернул JSON-структуру (отсутствуют фигурные скобки).")
    json_str = match.group(1)

    # Уровень 1: прямой парсинг
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # Уровень 2: висящие запятые перед } и ]
    repaired = re.sub(r",\s*([\]}])", r"\1", json_str)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Уровень 3: Python True/False/None → JSON true/false/null
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Уровень 4: одинарные кавычки → двойные (только если двойных нет совсем)
    if "'" in repaired and '"' not in repaired:
        candidate = repaired.replace("'", '"')
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Уровень 5: смешанный режим — одинарные ключи, двойные значения или наоборот
    if "'" in repaired:
        candidate = repaired.replace("'", '"')
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    print(f"[ИИ-Движок-Ошибка]: Не удалось восстановить JSON после всех уровней ремонта. "
          f"Сырой текст (обрезано): {json_str[:500]}")
    raise AIResponseParseError(f"ИИ вернул неисправимый формат данных после {5} попыток ремонта.")


class BaseProvider:
    """Базовый абстрактный класс провайдера ИИ с каскадным переключением (Failover Chain)."""

    # Признак локального провайдера (Ollama / LM Studio). Переопределяется в наследниках.
    is_local = False
    # Таймаут запроса по умолчанию. Локальные провайдеры увеличивают его.
    request_timeout = 30

    def __init__(self, api_key, model_pool, base_url=None):
        self.api_key = api_key
        self.model_pool = model_pool  # Список приоритетных моделей
        self.base_url = base_url      # Базовый URL (для локальных серверов)

    def make_request(self, model_name, contents, system_instruction):
        """Реализуется в дочерних классах провайдеров."""
        raise NotImplementedError

    def _classify_url_error(self, err, model_name):
        """
        Преобразует низкоуровневую сетевую ошибку urllib в структурированную
        ошибку движка. Для локальных серверов отказ соединения трактуется
        как 'сервер не запущен'.
        """
        reason = getattr(err, "reason", err)
        # Таймаут сокета.
        if isinstance(reason, socket.timeout) or isinstance(err, socket.timeout):
            return AITimeoutError(
                f"Таймаут ответа модели {model_name}. "
                + ("Локальная модель слишком медленная." if self.is_local else "Сервер не успел ответить.")
            )
        # Отказ соединения / хост недоступен.
        if isinstance(reason, (ConnectionError, ConnectionRefusedError, OSError)):
            if self.is_local:
                return AILocalServerError(
                    f"Локальный сервер {self.base_url} не отвечает. Запустите Ollama / LM Studio."
                )
            return AINetworkError(f"Сетевая ошибка соединения с моделью {model_name}: {reason}")
        return AINetworkError(f"Сетевой сбой модели {model_name}: {reason}")

    def call_with_failover(self, contents, system_instruction):
        """
        Failover Chain: последовательный обход пула моделей провайдера.
        При лимитах/таймаутах/5xx переходит к следующей модели. Бросает
        структурированную ошибку (AIEngineError-наследник) при полном провале.
        """
        # Локальным провайдерам ключ не нужен; проверяем только облачные.
        if not self.is_local and not self.api_key:
            raise AIAuthError("Ключ API отсутствует для выбранного провайдера.")
        if not self.model_pool:
            raise AIEngineError("Список активных моделей пуст. Выберите хотя бы одну модель.")

        last_exception = None
        for model_name in self.model_pool:
            print(f"[ИИ-Движок]: Запуск запроса на модели {model_name}...")
            for attempt in range(3):
                try:
                    return self.make_request(model_name, contents, system_instruction)
                except urllib.error.HTTPError as e:
                    status = e.code
                    last_exception = e

                    # Лимит частоты (429) или временный сбой сервера (502, 503, 504).
                    if status in (429, 502, 503, 504):
                        if status == 429:
                            last_exception = AIRateLimitError(
                                f"Лимит запросов (429) на модели {model_name}."
                            )
                        time.sleep(2 ** attempt)  # Экспоненциальный откат
                        continue

                    # Авторизация (401, 403) — нет смысла перебирать модели.
                    if status in (401, 403):
                        raise AIAuthError(
                            f"Ошибка авторизации API ({status}). Проверьте правильность ключа."
                        )

                    print(f"[ИИ-Движок]: Модель {model_name} вернула HTTP {status}. Пробуем следующую модель...")
                    last_exception = AINetworkError(
                        f"Модель {model_name} вернула HTTP-ошибку {status}."
                    )
                    break
                except urllib.error.URLError as e:
                    # Сетевой уровень: отказ соединения, таймаут, недоступный хост.
                    structured = self._classify_url_error(e, model_name)
                    print(f"[ИИ-Движок]: {structured.detail}")
                    last_exception = structured
                    # Для локального сервера, который не запущен, перебор моделей бессмыслен.
                    if isinstance(structured, AILocalServerError):
                        raise structured
                    time.sleep(1)
                    break
                except socket.timeout:
                    structured = AITimeoutError(f"Таймаут ответа модели {model_name}.")
                    print(f"[ИИ-Движок]: {structured.detail}")
                    last_exception = structured
                    time.sleep(1)
                    break
                except AIEngineError as e:
                    # Уже структурированная ошибка (например, пустой ответ модели).
                    print(f"[ИИ-Движок]: {e.detail}")
                    last_exception = e
                    break
                except Exception as e:
                    # Непредвиденный сбой — логируем с типом и переходим к следующей модели.
                    print(f"[ИИ-Движок]: Непредвиденный сбой модели {model_name} ({type(e).__name__}): {e}")
                    last_exception = AIEngineError(f"Непредвиденный сбой: {type(e).__name__}: {e}")
                    time.sleep(1)
                    break

        # Если последняя ошибка структурирована — пробрасываем её как есть.
        if isinstance(last_exception, AIEngineError):
            raise last_exception
        raise AIEngineError(
            f"Все модели в пуле провайдера завершились сбоем. Последняя ошибка: {last_exception}"
        )


class GeminiProvider(BaseProvider):
    """Провайдер Google Gemini API (поддержка 3-го поколения моделей)."""
    def make_request(self, model_name, contents, system_instruction):
        # ФИКС: Убран Markdown-синтаксис, ссылка теперь абсолютно чистая и валидная
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": contents}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.1}
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            
            # Защита от блокировок безопасности и пустого вывода
            candidates = res_data.get('candidates', [])
            if not candidates:
                block_reason = res_data.get('promptFeedback', {}).get('blockReason', 'Блокировка безопасности или пустой ответ')
                raise AIResponseParseError(f"Gemini API не вернул варианты ответа. Причина: {block_reason}")
                
            content = candidates[0].get('content', {})
            parts = content.get('parts', [])
            if not parts:
                raise AIResponseParseError("Ответ Gemini пуст или заблокирован фильтром контента.")
                
            return parts[0].get('text', '').strip()


class OpenAIProvider(BaseProvider):
    """Провайдер OpenAI API (совместимый с gpt-5 и o3 моделями)."""
    def make_request(self, model_name, contents, system_instruction):
        # ФИКС: Убран Markdown-синтаксис
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": contents}
            ],
            "temperature": 0.1
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            choices = res_data.get('choices', [])
            if not choices:
                raise AIResponseParseError("OpenAI API вернул пустой список вариантов.")
            return choices[0]['message']['content'].strip()


class AnthropicProvider(BaseProvider):
    """Провайдер Anthropic Claude API (поддержка claude-4-семейства)."""
    def make_request(self, model_name, contents, system_instruction):
        # ФИКС: Убран Markdown-синтаксис
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        payload = {
            "model": model_name,
            "system": system_instruction,
            "messages": [
                {"role": "user", "content": contents}
            ],
            "max_tokens": 2048,
            "temperature": 0.1
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data.get('content', [])
            if not content:
                raise AIResponseParseError("Anthropic API вернул пустой контент ответа.")
            return content[0].get('text', '').strip()


class DeepSeekProvider(BaseProvider):
    """Провайдер DeepSeek API."""
    def make_request(self, model_name, contents, system_instruction):
        # ФИКС: Убран Markdown-синтаксис
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": contents}
            ],
            "temperature": 0.1
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        
        with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            choices = res_data.get('choices', [])
            if not choices:
                raise AIResponseParseError("DeepSeek API вернул пустой список вариантов.")
            return choices[0]['message']['content'].strip()


class LMStudioProvider(BaseProvider):
    """
    Локальный провайдер LM Studio (OpenAI-совместимый API на порту 1234).
    Ключ не требуется. Применяются безопасные параметры генерации (guard clause),
    чтобы некорректные дефолты из UI LM Studio не ломали ответ.
    """
    is_local = True
    request_timeout = 120  # локальные модели медленнее облачных

    def __init__(self, api_key, model_pool, base_url=None):
        super().__init__(api_key or "local", model_pool, base_url or "http://localhost:1234")

    def make_request(self, model_name, contents, system_instruction):
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            # LM Studio игнорирует ключ, но заголовок не мешает.
            "Authorization": "Bearer local"
        }
        # Guard clause: жёстко навязываем безопасные параметры.
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": contents}
            ],
            "temperature": LOCAL_SAFE_PARAMS["temperature"],
            "top_p": LOCAL_SAFE_PARAMS["top_p"],
            "max_tokens": LOCAL_SAFE_PARAMS["max_tokens"],
            "frequency_penalty": LOCAL_SAFE_PARAMS["frequency_penalty"],
            "stream": False,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            choices = res_data.get('choices', [])
            if not choices:
                raise AIResponseParseError("LM Studio вернул пустой список вариантов.")
            message = choices[0].get('message', {})
            text = (message.get('content') or "").strip()
            if not text:
                raise AIResponseParseError("LM Studio вернул пустой текст ответа.")
            return text


class OllamaProvider(BaseProvider):
    """
    Локальный провайдер Ollama. Использует нативный эндпоинт /api/chat
    (порт 11434). Ключ не требуется. Безопасные параметры через 'options'.
    """
    is_local = True
    request_timeout = 120

    def __init__(self, api_key, model_pool, base_url=None):
        super().__init__(api_key or "local", model_pool, base_url or "http://localhost:11434")

    def _resolve_model(self, model_name: str) -> str:
        """Если model_name == 'local-model', определяет первую установленную модель через /api/tags."""
        if model_name != "local-model":
            return model_name
        try:
            tags_url = f"{self.base_url.rstrip('/')}/api/tags"
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                if models:
                    return models[0].get("name", "local-model")
        except Exception:
            pass
        raise AIEngineError(
            "В Ollama нет загруженных моделей. Установите модель командой: ollama pull <model_name>"
        )

    def make_request(self, model_name, contents, system_instruction):
        model_name = self._resolve_model(model_name)
        url = f"{self.base_url.rstrip('/')}/api/chat"
        headers = {"Content-Type": "application/json"}
        # Guard clause: безопасные options для Ollama.
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": contents}
            ],
            "stream": False,
            "options": {
                "temperature": LOCAL_SAFE_PARAMS["temperature"],
                "top_p": LOCAL_SAFE_PARAMS["top_p"],
                "num_predict": LOCAL_SAFE_PARAMS["max_tokens"],
                "num_ctx": LOCAL_SAFE_PARAMS["num_ctx"],
                "repeat_penalty": LOCAL_SAFE_PARAMS["repeat_penalty"],
            },
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=self.request_timeout) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            # Нативный формат Ollama: {"message": {"content": "..."}}
            message = res_data.get('message', {})
            text = (message.get('content') or "").strip()
            if not text:
                # Иногда Ollama (OpenAI-режим) кладёт ответ в choices.
                choices = res_data.get('choices', [])
                if choices:
                    text = (choices[0].get('message', {}).get('content') or "").strip()
            if not text:
                raise AIResponseParseError("Ollama вернула пустой текст ответа.")
            return text


def get_provider(provider_name, api_key, model_pool, base_url=None):
    """Фабричный метод инициализации нужного провайдера."""
    providers = {
        "Gemini": GeminiProvider,
        "OpenAI": OpenAIProvider,
        "Anthropic": AnthropicProvider,
        "DeepSeek": DeepSeekProvider,
        "Ollama": OllamaProvider,
        "LM Studio": LMStudioProvider
    }
    provider_cls = providers.get(provider_name)
    if not provider_cls:
        raise AIEngineError(f"Неизвестный провайдер: {provider_name}")
    # Локальные провайдеры принимают base_url.
    if provider_cls in (OllamaProvider, LMStudioProvider):
        return provider_cls(api_key, model_pool, base_url)
    return provider_cls(api_key, model_pool)


def check_local_server(provider_name, base_url=None, timeout=2.0):
    """
    Лёгкая проверка доступности локального сервера (для статус-плашки в UI).
    Возвращает (is_up: bool, message: str). Не бросает исключений.
      - Ollama:    GET {base}/api/tags
      - LM Studio: GET {base}/v1/models
    """
    defaults = {
        "Ollama": "http://localhost:11434",
        "LM Studio": "http://localhost:1234"
    }
    base = (base_url or defaults.get(provider_name, "")).rstrip("/")
    if not base:
        return False, "Неизвестный локальный провайдер."

    if provider_name == "Ollama":
        probe_url = f"{base}/api/tags"
    else:  # LM Studio и прочие OpenAI-совместимые
        probe_url = f"{base}/v1/models"

    try:
        req = urllib.request.Request(probe_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, "Локальный сервер активен"
            return False, f"Сервер ответил статусом {response.status}"
    except urllib.error.HTTPError as e:
        # Сервер жив, но эндпоинт вернул ошибку — считаем сервер запущенным.
        if e.code in (401, 403, 404):
            return True, "Локальный сервер активен"
        return False, f"Сервер вернул HTTP {e.code}"
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
        return False, "Локальный сервер не запущен. Проверьте Ollama / LM Studio."
    except Exception as e:
        print(f"[ИИ-Движок]: Непредвиденная ошибка проверки локального сервера ({type(e).__name__}): {e}")
        return False, "Не удалось проверить локальный сервер."


def _is_local_provider(provider_name):
    return provider_name in ("Ollama", "LM Studio")


def distill_resume(raw_text, config):
    """Однократная дистилляция сырого текста резюме через текущего провайдера ИИ."""
    provider_name = config.get("current_provider", "Gemini")
    api_keys = config.get("api_keys", {})
    is_local = _is_local_provider(provider_name)

    api_key = (api_keys.get(provider_name, "") or "").strip()
    if is_local and not api_key:
        api_key = "local"

    active_models = config.get("active_models", {})
    model_pool = active_models.get(provider_name, [])

    base_url = None
    if is_local:
        servers = config.get("local_servers", {}) or {}
        defaults = {"Ollama": "http://localhost:11434", "LM Studio": "http://localhost:1234"}
        base_url = servers.get(provider_name, defaults.get(provider_name))

    if not is_local and not api_key:
        raise AIAuthError("Отсутствует API ключ для провайдера.")
    if not model_pool:
        raise AIEngineError("Нет активных моделей для дистилляции резюме.")

    language = config.get("language", "en")
    lang_name = "Russian" if language == "ru" else "English"

    system_prompt = (
        "Analyze the raw resume text. Extract only: commercial technology stack, "
        "real work experience in years, key roles, and strong technical skills. "
        f"Answer strictly in {lang_name}. Be maximally dry, dense, and concise "
        "(200-300 tokens max). No soft skills, no greetings, no filler."
    )

    provider = get_provider(provider_name, api_key, model_pool, base_url)
    return provider.call_with_failover(raw_text[:8000], system_prompt)


def analyze_and_generate(vacancy, config):
    """
    Вызывает двухстадийный анализ вакансии через выбранного провайдера ИИ.
    stage1: фильтрация и извлечение структурированной информации в JSON.
    stage2: автогенерация качественного сопроводительного письма.

    Возвращает кортеж (status, text, extracted_data), где status ∈
    {"APPROVED", "REJECTED", "ERROR"}. При ошибке text — понятное
    структурированное описание (сеть / таймаут / парсинг / авторизация).
    """
    provider_name = config.get("current_provider", "Gemini")
    api_keys = config.get("api_keys", {})
    is_local = _is_local_provider(provider_name)

    # Для локальных провайдеров ключ не требуется — подставляем заглушку.
    api_key = (api_keys.get(provider_name, "") or "").strip()
    if is_local and not api_key:
        api_key = "local"

    active_models = config.get("active_models", {})
    model_pool = active_models.get(provider_name, [])

    # Базовый URL для локальных серверов.
    base_url = None
    if is_local:
        servers = config.get("local_servers", {}) or {}
        defaults = {"Ollama": "http://localhost:11434", "LM Studio": "http://localhost:1234"}
        base_url = servers.get(provider_name, defaults.get(provider_name))

    if not is_local and not api_key:
        return "ERROR", f"Отсутствует API ключ для провайдера {provider_name}.", {}
    if not model_pool:
        return "ERROR", f"Не выбрана ни одна рабочая модель для провайдера {provider_name}.", {}

    # Для локального провайдера сначала быстро проверяем, поднят ли сервер,
    # чтобы вернуть понятную ошибку вместо долгого таймаута на каждой модели.
    if is_local:
        is_up, msg = check_local_server(provider_name, base_url)
        if not is_up:
            return "ERROR", msg, {}

    language = config.get("language", "en")
    lang_name = "Russian" if language == "ru" else "English"

    raw_title = vacancy.get('title', 'Не указано')
    raw_text = vacancy.get('text', '')
    first_name = config.get("first_name", "Applicant")
    resume_text = config.get("resume", "")

    # Stage 1 reject-reason text for app-generated filter decisions
    _REJECT = {
        "remote":        {"en": "Remote work is not enabled in app settings.",
                          "ru": "Удалённая работа отключена в настройках приложения."},
        "office":        {"en": "Office work is not enabled in app settings.",
                          "ru": "Работа в офисе отключена в настройках приложения."},
        "hybrid":        {"en": "Hybrid work format is not enabled in app settings.",
                          "ru": "Гибридный формат работы отключён в настройках приложения."},
        "local":         {"en": "Position requires geographic presence.",
                          "ru": "Позиция требует географического присутствия."},
        "geo_excluded":  {"en": "Your location is excluded from this vacancy's work geography.",
                          "ru": "Ваша локация исключена из географии этой вакансии."},
        "geo_required":  {"en": "This vacancy requires presence in a specific region not matching your location.",
                          "ru": "Вакансия требует присутствия в регионе, не совпадающем с вашей локацией."},
        "fmt_unknown":   {"en": "Work format not specified; strict mode requires explicit format.",
                          "ru": "Формат работы не указан; строгий режим требует явного формата."},
    }

    def _reason(key):
        return _REJECT[key].get(language, _REJECT[key]["en"])

    def _geo_match(user_loc: str, regions: list) -> bool:
        """Case-insensitive substring match of user location against a list of regions."""
        u = user_loc.lower().strip()
        for r in regions:
            r_l = str(r).lower().strip()
            if u and r_l and (u in r_l or r_l in u):
                return True
        return False

    strictness = config.get("filter_strictness", 2)

    # Quality criteria blocks — assembled conditionally based on strictness level
    _s1_profession = (
        "=== REJECTION CRITERION 1: PROFESSION MISMATCH ===\n"
        "(is_relevant_profession: false if this applies)\n"
        "Role is clearly manual/unskilled labor not compatible with a professional profile.\n"
        "Always reject: drivers, couriers, cleaners, loaders, security guards, construction workers.\n"
        "If the candidate resume is EMPTY: reject only obvious unskilled labor — approve any legitimate "
        "white-collar role (IT, marketing, sales, admin, support, legal, finance, creative, etc.).\n\n"
    )
    _s1_scams = (
        "=== REJECTION CRITERION 2: SCAMS & ILLEGAL SCHEMES ===\n"
        "(Reject immediately if ANY of these apply)\n"
        "• MLM / network marketing / referral pyramid structures.\n"
        "• Esoterics, astrology, tarot, numerology, spiritual healing.\n"
        "• Required upfront payments: starter kits, mandatory paid training, software fees, 'refundable' deposits.\n"
        "• P2P crypto arbitrage, card farming/cashing, gambling/betting promotion, money laundering schemes.\n\n"
    )
    # Local/quantized models struggle with abstract reasoning — provide explicit keyword lists instead
    _s1_scams_local = (
        "=== REJECTION CRITERION 2: SCAMS & MLM — KEYWORD MATCH ===\n"
        "(Reject IMMEDIATELY if ANY of the following keywords or phrases appear anywhere in the vacancy text)\n"
        "Russian keywords: сетевой маркетинг, сетевой бизнес, сетевая структура, MLM, МЛМ, мультиуровневый маркетинг, "
        "реферальная сеть, реферальная программа, партнёрская программа, сеть дистрибьюторов, прямые продажи, "
        "дуплицирование, стартовый взнос, обязательный взнос, вступительный взнос, "
        "обучение за свой счёт, обязательный депозит, продажа на себе, "
        "таро, астрология, нумерология, эзотерика, "
        "P2P арбитраж, криптоарбитраж, картоарбитраж, карточный арбитраж.\n"
        "English keywords: network marketing, MLM, multi-level marketing, referral pyramid, "
        "upfront payment, mandatory deposit, starter kit fee, tarot, astrology, numerology, "
        "crypto arbitrage, P2P arbitrage, card cashing.\n"
        "IMPORTANT RULE: Do NOT reason about whether it 'might be' MLM or a scam. "
        "If ANY keyword above is present in the text → set is_relevant_profession: false immediately.\n\n"
    )

    scams_block = _s1_scams_local if is_local else _s1_scams

    _s1_exploitation = (
        "=== REJECTION CRITERION 3: SEVERE EXPLOITATION ===\n"
        "(Only reject when explicitly stated — never infer)\n"
        "• Calculated weekly hours strictly > 45 h (only when specific hours are given — do NOT guess from vague language).\n"
        "• Mandatory unpaid 24/7 on-call or permanent night shifts without stated extra compensation.\n"
        "• Mass-hiring / infobusiness red flags: 'групповые собеседования', 'массовый набор', 'поток кандидатов', "
        "'сетевой бизнес', 'партнёрская программа', 'обучение за свой счёт'.\n"
        "• Zero substance: only income slogans ('unlimited earnings', 'personal growth') with literally zero actual duties listed.\n\n"
    )
    _s1_soft_flags = (
        "=== REJECTION CRITERION 4: SOFT RED FLAGS (any TWO or more present → reject) ===\n"
        "• No company name or identifiable employer mentioned at all.\n"
        "• Duties section is absent or contains only generic phrases with zero role-specific content.\n"
        "• Requirements list is contradictory or impossibly broad (e.g., '5 years experience in 10 unrelated domains').\n"
        "• Salary completely absent for roles where disclosure is standard (specialist/senior level).\n"
        "• Excessive focus on personality traits or lifestyle with no mention of actual job deliverables.\n\n"
    )
    _s1_bias_mild = (
        "=== EVALUATION MODE: PERMISSIVE (MILD) ===\n"
        "Your only job: block obvious profession mismatches and clear scams (criteria 1 and 2 above). Let everything else through.\n"
        "Approve if: recognizable professional role + anything resembling a job description is present.\n"
        "Ignore ALL ambiguous signals. WHEN IN ANY DOUBT → APPROVE IMMEDIATELY.\n\n"
    )
    _s1_bias_balanced = (
        "=== EVALUATION MODE: BALANCED ===\n"
        "Approve if: recognizable professional role + at least some actual duties listed + reasonable overall terms.\n"
        "Ignore generic clichés ('dynamic team', 'results-oriented') when real duties are present.\n"
        "When in doubt on non-hard criteria → APPROVE. Minimize false positives.\n\n"
    )
    _s1_bias_strict = (
        "=== EVALUATION MODE: STRICT ===\n"
        "Quality over quantity — filter aggressively.\n"
        "Reject if ANY hard criterion (1–3) is met, OR if TWO OR MORE soft red flags from criterion 4 are present.\n"
        "Do NOT give benefit of the doubt on ambiguous quality signals. WHEN IN DOUBT → REJECT.\n\n"
    )

    if strictness == 1:
        _s1_quality_block = _s1_profession + scams_block + _s1_bias_mild
    elif strictness == 3:
        _s1_quality_block = _s1_profession + scams_block + _s1_exploitation + _s1_soft_flags + _s1_bias_strict
    else:  # 2 = BALANCED (default)
        _s1_quality_block = _s1_profession + scams_block + _s1_exploitation + _s1_bias_balanced

    stage1_system_instruction = (
        "You are a precise senior job quality filter agent. Evaluate the job posting and return structured JSON.\n\n"
        + _s1_quality_block +

        "=== WORK FORMAT — return 'work_formats' as a JSON array ===\n"
        "List ALL formats explicitly offered or clearly implied in the vacancy.\n"
        "Values: 'remote', 'office', 'hybrid'. Use 'unknown' ONLY if format is completely absent.\n"
        "RULES:\n"
        "  • If the vacancy offers MULTIPLE formats or says 'по договорённости' covering several options → include ALL of them.\n"
        "    Example: 'удалёнка / гибрид / офис по договорённости' → [\"remote\", \"hybrid\", \"office\"]\n"
        "    Example: 'возможна удалённая работа или офис' → [\"remote\", \"office\"]\n"
        "    Example: 'гибридный формат (2 дня дома, 3 в офисе)' → [\"hybrid\"]\n"
        "  • SEMANTIC CORRECTION: if title says 'Remote' but description clearly requires daily physical office presence → [\"office\"].\n"
        "  • If format is entirely unmentioned → [\"unknown\"].\n"
        "  • Do NOT guess format from job type — only report what is explicitly stated or contextually clear.\n\n"

        "=== WORKER GEOGRAPHY RESTRICTION ===\n"
        "Determine if the vacancy restricts WHERE THE WORKER must be physically located during work.\n"
        "This is about WORKER LOCATION, not about where the company office is situated.\n\n"
        "Return 'worker_geo_restriction' as one of:\n"
        "  'none'         — no restriction on worker location. Fully global / unrestricted.\n"
        "  'required_in'  — worker MUST be in listed regions. Only when EXPLICITLY stated for workers.\n"
        "  'excluded_from'— worker must NOT be in listed regions. Only for explicit bans.\n"
        "Return 'worker_geo_regions' as a list of region/country names the restriction applies to.\n\n"
        "CRITICAL RULES:\n"
        "1. Explicit global-remote phrases override everything: 'из любой точки мира', 'work from anywhere worldwide', "
        "'полностью удалённо без ограничений' → ALWAYS 'none', regions: [].\n"
        "2. Company/office city IS NOT a worker restriction. 'Офис в Москве', 'Где предстоит работать: Москва', "
        "'office: Berlin', 'headquarters: New York' → 'none', regions: [].\n"
        "3. Use 'required_in' ONLY when text explicitly says worker must be in X: "
        "'только из РФ', 'only candidates from Russia', 'must reside in', 'кандидаты только из'.\n"
        "4. Use 'excluded_from' ONLY when text explicitly bans workers from X: "
        "'outside Russia/Belarus', 'вне РФ и РБ', 'необходимо быть вне территории РФ'.\n"
        "5. When uncertain → 'none'. False positives cost users real job opportunities.\n\n"
        "Examples:\n"
        "  'Полностью удалённо из любой точки мира' → 'none', []\n"
        "  'Удалённо из любой точки (вне РФ, РБ, GMT+1–4)' → 'excluded_from', ['Russia','Belarus']\n"
        "  'Удалённо, только из РФ или РБ' → 'required_in', ['Russia','Belarus']\n"
        "  'Офис, Москва' → 'none', []    ← office location ≠ worker restriction\n"
        "  'Где предстоит работать: Москва' → 'none', []    ← site field, not worker restriction\n"
        "  'Remote' (no geo mentioned) → 'none', []\n\n"

        f"LANGUAGE: Write 'reject_reason', 'extracted_title', 'extracted_company' in {lang_name}.\n"
        "RESPONSE: raw JSON only — no markdown, no code blocks, no explanations.\n"
        "{\n"
        f'  "is_relevant_profession": boolean,\n'
        f'  "reject_reason": "string in {lang_name} explaining why (if false), else empty string",\n'
        f'  "extracted_title": "string — job title in {lang_name}",\n'
        f'  "extracted_company": "string — clean company name",\n'
        f'  "work_formats": ["remote" | "office" | "hybrid" | "unknown"],\n'
        f'  "worker_geo_restriction": "none" | "required_in" | "excluded_from",\n'
        f'  "worker_geo_regions": ["list", "of", "region", "names"]\n'
        "}"
    )
    
    stage1_prompt = f"Candidate Profile (Resume):\n{resume_text}\n\nJob Title: {raw_title}\n\nPage Text:\n{raw_text[:8000]}"

    try:
        provider = get_provider(provider_name, api_key, model_pool, base_url)
        res_text = provider.call_with_failover(stage1_prompt, stage1_system_instruction)
        
        # Задействуем интеллектуальный безопасный парсер JSON
        result_json = clean_and_parse_json(res_text)
        
        # Гарантируем наличие всех ключей
        extracted_title = result_json.get("extracted_title", raw_title)
        extracted_company = result_json.get("extracted_company", "Не указана")
        extracted_data = {"title": extracted_title, "company": extracted_company}

        # Если вакансия заблокирована ИИ по критериям адекватности
        if not result_json.get("is_relevant_profession", True):
            return "REJECTED", result_json.get("reject_reason", "Не прошло фильтр качества вакансий"), extracted_data

        # Parse work formats list (with fallback for old string field)
        raw_formats = result_json.get("work_formats", result_json.get("work_format", "unknown"))
        if isinstance(raw_formats, str):
            raw_formats = [raw_formats]
        valid_fmt = {"remote", "office", "hybrid"}
        work_formats = {f for f in raw_formats if f in valid_fmt}
        has_unknown_fmt = not work_formats  # no known format determined by AI

        f_remote = config.get("filter_remote", True)
        f_office = config.get("filter_office", False)
        f_hybrid = config.get("filter_hybrid", False)

        if (f_remote or f_office or f_hybrid):
            if work_formats:
                # Known formats returned — check intersection
                enabled = set()
                if f_remote: enabled.add("remote")
                if f_office: enabled.add("office")
                if f_hybrid: enabled.add("hybrid")
                if not (work_formats & enabled):
                    for fmt in ("remote", "hybrid", "office"):
                        if fmt in work_formats:
                            return "REJECTED", _reason(fmt), extracted_data
            elif has_unknown_fmt and strictness >= 3:
                # Strict mode: unknown format → reject
                return "REJECTED", _reason("fmt_unknown"), extracted_data

        # Geo restriction filter
        if config.get("filter_location") and config.get("user_location", "").strip():
            geo_restriction = result_json.get("worker_geo_restriction", "none")
            geo_regions = result_json.get("worker_geo_regions", [])
            user_loc = config.get("user_location", "").strip()

            if geo_restriction == "excluded_from" and _geo_match(user_loc, geo_regions):
                # Vacancy explicitly excludes the user's location
                return "REJECTED", _reason("geo_excluded"), extracted_data

            if geo_restriction == "required_in" and geo_regions and not _geo_match(user_loc, geo_regions):
                # Vacancy requires presence in a region that doesn't match user's location
                # Only reject for remote jobs — office jobs are handled by work_format filter
                # In MILD mode, skip rejection for unknown-format vacancies (might be office — let it through)
                if "remote" in work_formats or (has_unknown_fmt and strictness >= 2):
                    return "REJECTED", _reason("geo_required"), extracted_data

    except AILocalServerError as e:
        return "ERROR", e.detail, {}
    except AITimeoutError as e:
        return "ERROR", f"Таймаут локальной модели на Stage 1: {e.detail}", {}
    except AIAuthError as e:
        return "ERROR", f"Stage 1 — {e.detail}", {}
    except AIResponseParseError as e:
        return "ERROR", f"Stage 1 — модель вернула некорректный ответ: {e.detail}", {}
    except AINetworkError as e:
        return "ERROR", f"Stage 1 — сетевая ошибка: {e.detail}", {}
    except AIEngineError as e:
        return "ERROR", f"Сбой каскада ИИ на Stage 1: {e.detail}", {}
    except Exception as e:
        print(f"[ИИ-Движок]: Непредвиденный сбой Stage 1 ({type(e).__name__}): {e}")
        return "ERROR", f"Непредвиденный сбой на Stage 1: {type(e).__name__}: {e}", {}

    # Запускаем Stage 2: генерация сопроводительного письма
    closing = "С уважением" if language == "ru" else "Best regards"

    letter_length = config.get("letter_length", 2)
    if letter_length == 1:
        length_instruction = (
            "Write exactly 1 paragraph (3–4 sentences maximum). "
            "State who you are, the role you are applying for, and your single strongest qualification match from the resume. "
            "Be direct and specific. No background story, no company praise, no filler phrases."
        )
    elif letter_length == 3:
        length_instruction = (
            "Write exactly 4–5 paragraphs using this exact structure:\n"
            "1. Introduction — your current professional role and genuine, specific motivation for this position.\n"
            "2. Professional background — concise relevant experience that matches the vacancy requirements.\n"
            "3. Key achievements — 2–3 concrete accomplishments from the resume that directly apply to this role.\n"
            "4. Company alignment — why this specific company appeals to you, based on what the vacancy reveals.\n"
            "5. Closing — confident call to action inviting the next step."
        )
    else:  # 2 = BALANCED (default)
        length_instruction = (
            "Write 2–3 concise paragraphs:\n"
            "1. Opening — briefly who you are and why this specific role interests you.\n"
            "2. Core match — your top 2 most relevant skills or experiences from the resume that fit this vacancy.\n"
            "3. Closing — brief, confident call to action."
        )

    local_guard = (
        "\n\nSTRICT ANTI-HALLUCINATION RULE: Only mention skills, tools, technologies, frameworks, "
        "and experiences that are EXPLICITLY written in the resume provided below. "
        "Do NOT add, infer, or assume any capability not literally present in the resume text. "
        "If a skill or tool is not mentioned in the resume — do not write about it."
    ) if getattr(provider, "is_local", False) else ""

    stage2_system_instruction = (
        f"You are an HR expert. Write a professional cover letter on behalf of {first_name}. "
        f"The letter MUST be written entirely in {lang_name} language. No fluff.\n\n"
        f"STRUCTURE AND LENGTH REQUIREMENT:\n{length_instruction}\n\n"
        f"At the very end of the letter, MANDATORILY add the closing signature: '{closing}, {first_name}'.{local_guard}"
    )
    stage2_prompt = f"Resume:\n{resume_text}\n\nVacancy: {extracted_title} in company {extracted_company}\nDescription:\n{raw_text[:4000]}"

    try:
        letter_text = provider.call_with_failover(stage2_prompt, stage2_system_instruction)
        return "APPROVED", letter_text, extracted_data
    except AILocalServerError as e:
        return "ERROR", e.detail, extracted_data
    except AITimeoutError as e:
        return "ERROR", f"Таймаут локальной модели на Stage 2: {e.detail}", extracted_data
    except AIAuthError as e:
        return "ERROR", f"Stage 2 — {e.detail}", extracted_data
    except AINetworkError as e:
        return "ERROR", f"Stage 2 — сетевая ошибка: {e.detail}", extracted_data
    except AIEngineError as e:
        return "ERROR", f"Сбой каскада ИИ на Stage 2: {e.detail}", extracted_data
    except Exception as e:
        print(f"[ИИ-Движок]: Непредвиденный сбой Stage 2 ({type(e).__name__}): {e}")
        return "ERROR", f"Непредвиденный сбой на Stage 2: {type(e).__name__}: {e}", extracted_data