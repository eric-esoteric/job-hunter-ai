import json
import os
import threading

# Путь к системной папке AppData\Roaming для текущего пользователя Windows.
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Job Hunter AI')

_file_lock = threading.Lock()

# In-memory URL caches — populated lazily on first dedup check, updated on every
# write/delete so we never read the entire JSON file per-request.
# None means "not yet built"; an empty set means "file is empty".
_approved_url_cache: "set | None" = None
_rejected_url_cache: "set | None" = None


def _build_url_set_unlocked(filepath: str) -> set:
    """Read URL set directly from a vacancy file. Caller must hold _file_lock."""
    if not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {v.get("url") for v in data if v.get("url") and v.get("url") != "#"}
    except Exception:
        return set()

# Автоматически создаем папку "Job Hunter AI" в AppData, если её ещё нет на компьютере.
os.makedirs(APPDATA_DIR, exist_ok=True)

# Указываем абсолютные безопасные пути к файлам баз данных вакансий и конфигурации.
APPROVED_FILE = os.path.join(APPDATA_DIR, "saved_vacancies.json")
REJECTED_FILE = os.path.join(APPDATA_DIR, "rejected_vacancies.json")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")
RESUMES_FILE = os.path.join(APPDATA_DIR, "resume_history.json")

def _migrate_strip_description():
    """
    One-time startup migration: removes the 'description' (raw page text) field
    from all approved vacancy records written by old sessions. Those sessions stored
    document.body.innerText per record (up to several MB each), which made
    _modify_file() hold _file_lock long enough to time out extension requests.
    No-op when the file is already clean or does not exist.
    Runs before any Flask/worker threads start, so no lock is needed.
    """
    if not os.path.exists(APPROVED_FILE):
        return
    try:
        with open(APPROVED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not any("description" in v for v in data):
            return
        cleaned = [{k: val for k, val in v.items() if k != "description"} for v in data]
        with open(APPROVED_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=4)
        print(f"[Migration]: Removed 'description' from {len(cleaned)} approved vacancy records.")
    except Exception as e:
        print(f"[Migration]: Could not strip descriptions from approved file: {e}")

def init_db():
    """Создает пустые файлы баз данных, если они отсутствуют."""
    if not os.path.exists(APPROVED_FILE):
        _save_file(APPROVED_FILE, [])
    if not os.path.exists(REJECTED_FILE):
        _save_file(REJECTED_FILE, [])
    _migrate_strip_description()

def _load_file(filepath):
    """Безопасно загружает данные из JSON файла (без блокировки — только для чтения)."""
    with _file_lock:
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"[Хранилище]: Повреждён JSON в {filepath}: {e}. Возвращён пустой список.")
            return []
        except OSError as e:
            print(f"[Хранилище]: Ошибка чтения {filepath}: {e}. Возвращён пустой список.")
            return []

def _save_file(filepath, data):
    """Записывает данные в файл в формате UTF-8."""
    with _file_lock:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Ошибка сохранения]: Не удалось записать файл {filepath}. Причина: {e}")

def _modify_file(filepath, mutate_fn):
    """
    Атомарный read-modify-write под единым захватом _file_lock.
    mutate_fn(data: list) -> list — чистая функция преобразования списка.
    Устраняет TOCTOU-гонку между параллельными save/delete/clear операциями.
    """
    with _file_lock:
        if not os.path.exists(filepath):
            data = []
        else:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"[Хранилище]: Ошибка чтения при модификации {filepath}: {e}. Начинаем с пустого списка.")
                data = []
        data = mutate_fn(data)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Хранилище]: Не удалось записать {filepath}: {e}")

def load_config():
    """Безопасно загружает расширенную конфигурацию приложения с дефолтными значениями."""
    default_config = {
        "first_name": "",
        "last_name": "",
        "resume": "",
        "filter_remote": True,
        "filter_office": False,
        "filter_hybrid": False,
        "filter_no_rf": True,
        "filter_location": True,
        "user_location": "USA",
        "filter_strictness": 2,
        "letter_length": 2,
        "notifications_enabled": True,
        "resume_history": [],
        "current_provider": "Gemini",
        "api_keys": {
            "Gemini": "",
            "OpenAI": "",
            "Anthropic": "",
            "DeepSeek": "",
            "Ollama": "local",
            "LM Studio": "local"
        },
        "active_models": {
            "Gemini": ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
            "OpenAI": ["gpt-5-mini"],
            "Anthropic": ["claude-4-haiku"],
            "DeepSeek": ["deepseek-chat"],
            "Ollama": ["local-model"],
            "LM Studio": ["local-model"]
        },
        "request_delay": 15,
        # Показывать модальное предупреждение о требованиях к скорости локальных LLM.
        # Сбрасывается в False, если пользователь отметит "Больше не показывать".
        "show_local_llm_warning": True,
        # Базовые URL локальных серверов (можно переопределить вручную в config.json).
        "local_servers": {
            "Ollama": "http://localhost:11434",
            "LM Studio": "http://localhost:1234"
        },
        "language": "en"
    }
    
    if not os.path.exists(CONFIG_FILE):
        _save_file(CONFIG_FILE, default_config)
        return default_config
        
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            # Бережно обновляем отсутствующие ключи в пользовательском конфиге
            for key, val in default_config.items():
                if key not in user_config:
                    user_config[key] = val
                elif isinstance(val, dict) and isinstance(user_config[key], dict):
                    for sub_key, sub_val in val.items():
                        if sub_key not in user_config[key]:
                            user_config[key][sub_key] = sub_val
            
            # Миграция filter_no_rf → filter_location + user_location
            if "filter_location" not in user_config and "filter_no_rf" in user_config:
                user_config["filter_location"] = bool(user_config["filter_no_rf"])
                lang = user_config.get("language", "en")
                user_config["user_location"] = "Russia" if lang == "ru" else "United States"
                _save_file(CONFIG_FILE, user_config)
                print("[Миграция]: filter_no_rf → filter_location выполнена.")

            # Автоматическая миграция устаревших моделей Gemini на 2026 год
            if "active_models" in user_config and "Gemini" in user_config["active_models"]:
                gemini_active = user_config["active_models"]["Gemini"]
                migrated = False
                for idx, model in enumerate(gemini_active):
                    if model == "gemini-3.1-flash":
                        gemini_active[idx] = "gemini-3.1-flash-lite"
                        migrated = True
                    elif model == "gemini-3.0-pro":
                        gemini_active[idx] = "gemini-3.1-pro"
                        migrated = True
                if migrated:
                    seen = set()
                    user_config["active_models"]["Gemini"] = [x for x in gemini_active if not (x in seen or seen.add(x))]
                    _save_file(CONFIG_FILE, user_config)
                    print("[Сборщик-Миграция]: Конфигурация Gemini успешно обновлена.")

            # Миграция Ollama: старые захардкоженные имена моделей → "local-model"
            if "active_models" in user_config and "Ollama" in user_config["active_models"]:
                ollama_models = user_config["active_models"]["Ollama"]
                if isinstance(ollama_models, list) and ollama_models and "local-model" not in ollama_models:
                    user_config["active_models"]["Ollama"] = ["local-model"]
                    _save_file(CONFIG_FILE, user_config)
                    print("[Сборщик-Миграция]: Конфигурация Ollama обновлена до local-model.")

            return user_config
    except json.JSONDecodeError as e:
        print(f"[Конфигурация]: Файл config.json повреждён (JSON): {e}. Используются значения по умолчанию.")
        return default_config
    except OSError as e:
        print(f"[Конфигурация]: Ошибка чтения config.json: {e}. Используются значения по умолчанию.")
        return default_config
    except Exception as e:
        print(f"[Конфигурация]: Непредвиденная ошибка загрузки config.json: {e}. Используются значения по умолчанию.")
        return default_config

def save_config(config_data):
    """Сохраняет конфигурацию приложения в AppData."""
    _save_file(CONFIG_FILE, config_data)

def is_local_provider(provider_name):
    """Возвращает True для локальных провайдеров (Ollama / LM Studio)."""
    return provider_name in ("Ollama", "LM Studio")

def get_local_server_url(provider_name, config=None):
    """
    Возвращает базовый URL локального сервера для провайдера.
    Если config не передан — берёт дефолтные значения.
    """
    defaults = {
        "Ollama": "http://localhost:11434",
        "LM Studio": "http://localhost:1234"
    }
    if config is None:
        return defaults.get(provider_name, "")
    servers = config.get("local_servers", {}) or {}
    return servers.get(provider_name, defaults.get(provider_name, ""))

def should_show_local_warning(config=None):
    """Нужно ли показать предупреждение о локальных LLM (флаг или его отсутствие)."""
    if config is None:
        config = load_config()
    return bool(config.get("show_local_llm_warning", True))

def set_show_local_warning(value):
    """Сохраняет флаг показа предупреждения о локальных LLM в config.json."""
    config = load_config()
    config["show_local_llm_warning"] = bool(value)
    save_config(config)

def save_approved_vacancy(company, title, url, cover_letter="", description=""):
    """Атомарно добавляет новую одобренную ИИ вакансию в список."""
    global _approved_url_cache
    # description (raw page text) intentionally not stored — can be hundreds of KB
    # per vacancy, is never read back from the file, and would make _modify_file()
    # progressively slower with each new record, causing request timeouts at scale.
    new_vacancy = {
        "company": company,
        "title": title,
        "url": url,
        "cover_letter": cover_letter,
    }
    _modify_file(APPROVED_FILE, lambda data: data + [new_vacancy])
    with _file_lock:
        if _approved_url_cache is not None and url and url != "#":
            _approved_url_cache.add(url)

def save_rejected_vacancy(company, title, url, reason=""):
    """Атомарно добавляет отклоненную вакансию в журнал (макс 50 записей)."""
    global _rejected_url_cache
    new_vacancy = {"company": company, "title": title, "url": url, "reason": reason}
    def _append_capped(data):
        data.append(new_vacancy)
        return data[-50:] if len(data) > 50 else data
    _modify_file(REJECTED_FILE, _append_capped)
    with _file_lock:
        if _rejected_url_cache is not None and url and url != "#":
            _rejected_url_cache.add(url)

def get_all_approved():
    """Возвращает список всех сохраненных вакансий."""
    return _load_file(APPROVED_FILE)

def get_all_rejected():
    """Возвращает список всех отклоненных вакансий."""
    return _load_file(REJECTED_FILE)

def delete_vacancy_by_url(url):
    """Атомарно удаляет одобренную вакансию по URL."""
    global _approved_url_cache
    _modify_file(APPROVED_FILE, lambda data: [v for v in data if v.get("url") != url])
    with _file_lock:
        if _approved_url_cache is not None:
            _approved_url_cache.discard(url)

def delete_rejected_by_url(url):
    """Атомарно удаляет отклоненную вакансию по URL."""
    global _rejected_url_cache
    _modify_file(REJECTED_FILE, lambda data: [v for v in data if v.get("url") != url])
    with _file_lock:
        if _rejected_url_cache is not None:
            _rejected_url_cache.discard(url)

def clear_all_vacancies():
    """Атомарно очищает базу данных одобренных."""
    global _approved_url_cache
    _modify_file(APPROVED_FILE, lambda _: [])
    with _file_lock:
        _approved_url_cache = None

def clear_all_rejected():
    """Атомарно очищает базу данных отклоненных."""
    global _rejected_url_cache
    _modify_file(REJECTED_FILE, lambda _: [])
    with _file_lock:
        _rejected_url_cache = None

def vacancy_url_in_approved(url: str) -> bool:
    """Проверяет наличие URL в одобренных вакансиях (O(1) через in-memory кеш)."""
    global _approved_url_cache
    if not url or url == "#":
        return False
    with _file_lock:
        cache = _approved_url_cache
        if cache is None:
            _approved_url_cache = _build_url_set_unlocked(APPROVED_FILE)
            cache = _approved_url_cache
        return url in cache

def vacancy_url_in_rejected(url: str) -> bool:
    """Проверяет наличие URL в отклонённых вакансиях (O(1) через in-memory кеш)."""
    global _rejected_url_cache
    if not url or url == "#":
        return False
    with _file_lock:
        cache = _rejected_url_cache
        if cache is None:
            _rejected_url_cache = _build_url_set_unlocked(REJECTED_FILE)
            cache = _rejected_url_cache
        return url in cache

def get_resume_history() -> list:
    """Возвращает список сохранённых резюме [{name, text}]."""
    return _load_file(RESUMES_FILE) or []

def save_resume_to_history(name: str, text: str) -> None:
    """Добавляет или обновляет резюме в истории по имени."""
    history = get_resume_history()
    for item in history:
        if item.get("name") == name:
            item["text"] = text
            _save_file(RESUMES_FILE, history)
            return
    history.append({"name": name, "text": text})
    _save_file(RESUMES_FILE, history)

def delete_resume_from_history(name: str) -> None:
    """Удаляет резюме из истории по имени."""
    history = [r for r in get_resume_history() if r.get("name") != name]
    _save_file(RESUMES_FILE, history)