import json
import os
import tempfile
import threading
from jh_log import get_logger

logger = get_logger(__name__)

# Путь к системной папке AppData\Roaming для текущего пользователя Windows.
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Job Hunter AI')

_file_lock = threading.Lock()
# Dedicated lock for the URL sets only. Held for microseconds (set operations).
# NEVER acquired while _file_lock is held, and vice-versa — no nesting, no deadlock.
_url_lock = threading.Lock()

# Always-live URL sets: populated at startup by init_db(), mutated on every
# save/delete/clear. Never None — no cold-path file reads during live requests.
_approved_urls: set = set()
_rejected_urls: set = set()


def _build_url_set_unlocked(filepath: str) -> set:
    """Read URL set from a vacancy file. Caller must ensure no concurrent writes."""
    if not os.path.exists(filepath):
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {v.get("url") for v in data if v.get("url") and v.get("url") != "#"}
    except Exception:
        logger.warning(f"[Хранилище]: Не удалось построить набор URL из {filepath}", exc_info=True)
        return set()

# Автоматически создаем папку "Job Hunter AI" в AppData, если её ещё нет на компьютере.
os.makedirs(APPDATA_DIR, exist_ok=True)

# Указываем абсолютные безопасные пути к файлам баз данных вакансий и конфигурации.
APPROVED_FILE = os.path.join(APPDATA_DIR, "saved_vacancies.json")
REJECTED_FILE = os.path.join(APPDATA_DIR, "rejected_vacancies.json")
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")
RESUMES_FILE = os.path.join(APPDATA_DIR, "resume_history.json")

def _migrate_strip_description() -> None:
    """
    One-time startup migration: removes the 'description' (raw page text) field
    from all approved vacancy records written by old sessions.

    Runs synchronously before any background threads start, so holding
    _file_lock here introduces zero contention. Delegates the write to
    _write_json_atomic so a power fault mid-migration cannot corrupt the file.
    No-op when the file is already clean or does not exist.
    """
    with _file_lock:
        if not os.path.exists(APPROVED_FILE):
            return
        try:
            with open(APPROVED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            # unreadable on startup — let init_db() establish a fresh state
            logger.debug("[Migration]: approved file unreadable, skipping", exc_info=True)
            return

        migrated = False
        for item in data:
            if "description" in item:
                del item["description"]
                migrated = True

        if not migrated:
            return

        try:
            _write_json_atomic(APPROVED_FILE, data)
            logger.info(f"[Migration]: Removed 'description' from {len(data)} approved vacancy records.")
        except RuntimeError as exc:
            logger.warning(f"[Migration]: {exc}")

def _sweep_stale_tmp_files() -> None:
    """
    Remove orphaned atomic-write temp files left behind if the process was
    hard-killed (e.g. os._exit) mid-write. The temp files use the "jh_" prefix
    (see _write_json_atomic) and the theme writer's "ls_" prefix. Safe to run
    at startup while single-threaded — no live writer can own them yet.
    """
    try:
        for name in os.listdir(APPDATA_DIR):
            if (name.startswith("jh_") or name.startswith("ls_")) and name.endswith(".tmp"):
                try:
                    os.remove(os.path.join(APPDATA_DIR, name))
                except OSError:
                    logger.debug("Suppressed exception", exc_info=True)
    except OSError:
        logger.debug("Suppressed exception", exc_info=True)


def init_db():
    """Создает пустые файлы баз данных, если они отсутствуют."""
    _sweep_stale_tmp_files()
    if not os.path.exists(APPROVED_FILE):
        _save_file(APPROVED_FILE, [])
    if not os.path.exists(REJECTED_FILE):
        _save_file(REJECTED_FILE, [])
    _migrate_strip_description()
    # Populate URL sets from disk before Flask/worker threads start.
    # Single-threaded here — no lock needed, safe to read files directly.
    _approved_urls.clear()
    _approved_urls.update(_build_url_set_unlocked(APPROVED_FILE))
    _rejected_urls.clear()
    _rejected_urls.update(_build_url_set_unlocked(REJECTED_FILE))

def _load_file(filepath):
    """Безопасно загружает данные из JSON файла (без блокировки — только для чтения)."""
    with _file_lock:
        if not os.path.exists(filepath):
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"[Хранилище]: Повреждён JSON в {filepath}: {e}. Возвращён пустой список.")
            return []
        except OSError as e:
            logger.error(f"[Хранилище]: Ошибка чтения {filepath}: {e}. Возвращён пустой список.")
            return []

def _write_json_atomic(filepath: str, data) -> None:
    """
    Writes data to filepath using the write-to-temp → fsync → replace pattern.

    MUST be called while _file_lock is already held by the caller.

    Crash-safety guarantee: either the rename succeeds (new content visible) or
    the original file is completely untouched.  The O_TRUNC truncation that
    normally zeroes the destination file before writing is avoided entirely.

    The temp file is created in the same directory as filepath so that
    os.replace() is a same-partition rename — guaranteed atomic on POSIX/Win32.
    """
    dir_name = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="jh_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())   # flush OS kernel buffers to physical storage
        os.replace(tmp_path, filepath)
    except Exception as exc:
        try:
            os.remove(tmp_path)
        except OSError:
            logger.debug("Suppressed exception", exc_info=True)
        raise RuntimeError(f"Atomic write failed for {filepath}: {exc}")


def _save_file(filepath, data):
    """Atomically writes data to a JSON file (power-failure safe)."""
    with _file_lock:
        try:
            _write_json_atomic(filepath, data)
        except Exception as e:
            logger.error(f"[Хранилище]: Не удалось записать {filepath}: {e}")


def _modify_file(filepath: str, mutation_callback) -> bool:
    """
    Atomically reads, mutates, and writes a JSON database file.

    mutation_callback(data: list) -> list — pure transformation function.
    Eliminates the TOCTOU race between concurrent save/delete/clear operations
    and protects against data loss on crash (write-copy-replace pattern).

    Returns True on success, False on I/O failure.  Callers MUST check the
    return value before updating in-memory URL sets — if the disk write fails
    the sets must NOT be mutated so they stay in sync with physical storage.
    """
    with _file_lock:
        current_data = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    current_data = json.load(f)
            except Exception:
                current_data = []   # recover from corruption: start fresh

        mutated_data = mutation_callback(current_data)

        try:
            _write_json_atomic(filepath, mutated_data)
            return True
        except RuntimeError as exc:
            logger.warning(f"[Хранилище]: {exc}")
            return False

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
        # Hard country gate (jh_ai_engine.analyze_and_generate): when set, any
        # vacancy whose extracted "vacancy_country" doesn't match is rejected
        # outright. Empty string disables the gate.
        "target_country": "",
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
            "OpenRouter": "",
            "Ollama": "local",
            "LM Studio": "local"
        },
        "active_models": {
            "Gemini": ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
            "OpenAI": ["gpt-5-mini"],
            "Anthropic": ["claude-4-haiku"],
            "DeepSeek": ["deepseek-chat"],
            "OpenRouter": ["openai/gpt-5-mini"],
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
        "language": "en",
        # Structured hotkey dict — replaces the legacy "capture_hotkey" string.
        # Edited via the visual selector in AI Settings (no raw text entry).
        "hotkey": {"mod1": "ctrl", "mod2": "shift", "key": "X"},
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
                logger.info("[Миграция]: filter_no_rf → filter_location выполнена.")

            # Автоматическая миграция устаревших моделей Gemini на 2026 год
            if "active_models" in user_config and "Gemini" in user_config["active_models"]:
                gemini_active = user_config["active_models"]["Gemini"]
                migrated = False
                for idx, model in enumerate(gemini_active):
                    if model == "gemini-3.1-flash":
                        gemini_active[idx] = "gemini-3.1-flash-lite"
                        migrated = True
                if migrated:
                    seen = set()
                    user_config["active_models"]["Gemini"] = [x for x in gemini_active if not (x in seen or seen.add(x))]
                    _save_file(CONFIG_FILE, user_config)
                    logger.info("[Сборщик-Миграция]: Конфигурация Gemini успешно обновлена.")

            # Миграция Ollama: старые захардкоженные имена моделей → "local-model"
            if "active_models" in user_config and "Ollama" in user_config["active_models"]:
                ollama_models = user_config["active_models"]["Ollama"]
                if isinstance(ollama_models, list) and ollama_models and "local-model" not in ollama_models:
                    user_config["active_models"]["Ollama"] = ["local-model"]
                    _save_file(CONFIG_FILE, user_config)
                    logger.info("[Сборщик-Миграция]: Конфигурация Ollama обновлена до local-model.")

            # Migrate legacy "capture_hotkey" pynput string → structured "hotkey" dict.
            # Runs once; the old key is removed so this branch is never entered again.
            if "capture_hotkey" in user_config and not isinstance(
                user_config.get("hotkey"), dict
            ):
                old_str = user_config.pop("capture_hotkey", "")
                alias   = {"control": "ctrl", "cmd": "win", "command": "win", "super": "win"}
                parts   = [p.strip().strip("<>").lower() for p in old_str.split("+") if p.strip()]
                mods    = []
                key     = ""
                for p in parts:
                    p = alias.get(p, p)
                    if p in ("ctrl", "alt", "shift", "win"):
                        mods.append(p)
                    elif len(p) == 1 and p.isalpha():
                        key = p.upper()
                user_config["hotkey"] = {
                    "mod1": mods[0] if mods else "ctrl",
                    "mod2": mods[1] if len(mods) > 1 else "shift",
                    "key":  key or "X",
                }
                _save_file(CONFIG_FILE, user_config)
                logger.info("[Migration]: 'capture_hotkey' string → 'hotkey' dict completed.")

            return user_config
    except json.JSONDecodeError as e:
        logger.error(f"[Конфигурация]: Файл config.json повреждён (JSON): {e}. Используются значения по умолчанию.")
        return default_config
    except OSError as e:
        logger.error(f"[Конфигурация]: Ошибка чтения config.json: {e}. Используются значения по умолчанию.")
        return default_config
    except Exception as e:
        logger.error(f"[Конфигурация]: Непредвиденная ошибка загрузки config.json: {e}. Используются значения по умолчанию.")
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

def save_approved_vacancy(company, title, url, cover_letter="", description="", vacancy_country=""):
    """Атомарно добавляет новую одобренную ИИ вакансию в список."""
    # description (raw page text) intentionally not stored — can be hundreds of KB
    # per vacancy, is never read back from the file, and would make _modify_file()
    # progressively slower with each new record, causing request timeouts at scale.
    new_vacancy = {
        "company": company,
        "title": title,
        "url": url,
        "cover_letter": cover_letter,
        # Country extracted by the AI engine's Stage 1 gate (may be "" if
        # undeterminable, or if the vacancy was processed before this field
        # was introduced — see _with_country_default() on the read path).
        "vacancy_country": vacancy_country or "",
    }
    if _modify_file(APPROVED_FILE, lambda data: data + [new_vacancy]):
        if url and url != "#":
            with _url_lock:
                _approved_urls.add(url)

def save_rejected_vacancy(company, title, url, reason="", vacancy_country=""):
    """Атомарно добавляет отклоненную вакансию в журнал (макс 50 записей)."""
    new_vacancy = {
        "company": company,
        "title": title,
        "url": url,
        "reason": reason,
        "vacancy_country": vacancy_country or "",
    }
    _capped_ref = {}

    def _append_capped(data):
        data.append(new_vacancy)
        capped = data[-50:] if len(data) > 50 else data
        _capped_ref["data"] = capped
        return capped

    if _modify_file(REJECTED_FILE, _append_capped):
        # Rebuild the in-memory set from the CAPPED list, not by blindly adding
        # the new URL. Records evicted by the 50-item cap must also drop out of
        # the set — otherwise the set grows unbounded and keeps reporting
        # evicted vacancies as "already rejected", so they can never be
        # re-evaluated (they'd be silently skipped by the dedup check forever).
        with _url_lock:
            _rejected_urls.clear()
            _rejected_urls.update(
                v.get("url")
                for v in _capped_ref.get("data", [])
                if v.get("url") and v.get("url") != "#"
            )

def _with_country_default(records: list) -> list:
    """
    Deserialization compatibility shim: records written before the
    'vacancy_country' field existed won't have the key on disk. Backfill it
    in-memory on read so downstream code (UI, filters, exports) can always
    rely on the key being present without special-casing old records.
    Does not rewrite the file — purely a read-time default.
    """
    for record in records:
        record.setdefault("vacancy_country", "")
    return records

def get_all_approved():
    """Возвращает список всех сохраненных вакансий."""
    return _with_country_default(_load_file(APPROVED_FILE))

def get_all_rejected():
    """Возвращает список всех отклоненных вакансий."""
    return _with_country_default(_load_file(REJECTED_FILE))

def delete_vacancy_by_url(url):
    """Атомарно удаляет одобренную вакансию по URL."""
    if _modify_file(APPROVED_FILE, lambda data: [v for v in data if v.get("url") != url]):
        with _url_lock:
            _approved_urls.discard(url)

def delete_rejected_by_url(url):
    """Атомарно удаляет отклоненную вакансию по URL."""
    if _modify_file(REJECTED_FILE, lambda data: [v for v in data if v.get("url") != url]):
        with _url_lock:
            _rejected_urls.discard(url)

def clear_all_vacancies():
    """Атомарно очищает базу данных одобренных."""
    if _modify_file(APPROVED_FILE, lambda _: []):
        with _url_lock:
            _approved_urls.clear()

def clear_all_rejected():
    """Атомарно очищает базу данных отклоненных."""
    if _modify_file(REJECTED_FILE, lambda _: []):
        with _url_lock:
            _rejected_urls.clear()

def vacancy_url_in_approved(url: str) -> bool:
    """O(1) check against the live in-memory set. Only _url_lock — never waits on I/O."""
    if not url or url == "#":
        return False
    with _url_lock:
        return url in _approved_urls

def vacancy_url_in_rejected(url: str) -> bool:
    """O(1) check against the live in-memory set. Only _url_lock — never waits on I/O."""
    if not url or url == "#":
        return False
    with _url_lock:
        return url in _rejected_urls

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
