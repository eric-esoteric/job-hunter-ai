import json
import os

# Находим путь к системной папке AppData\Roaming для текущего пользователя Windows.
# Если это не Windows, используем домашнюю директорию как резервный вариант.
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Job Hunter AI')

# Автоматически создаем папку "Job Hunter AI" в AppData, если её ещё нет на компьютере.
# Это предотвращает любые ошибки отсутствия папки при первом запуске.
os.makedirs(APPDATA_DIR, exist_ok=True)

# Указываем абсолютные безопасные пути к файлам баз данных вакансий.
APPROVED_FILE = os.path.join(APPDATA_DIR, "saved_vacancies.json")
REJECTED_FILE = os.path.join(APPDATA_DIR, "rejected_vacancies.json")

def init_db():
    """Создает пустые файлы баз данных, если они отсутствуют."""
    if not os.path.exists(APPROVED_FILE):
        _save_file(APPROVED_FILE, [])
    if not os.path.exists(REJECTED_FILE):
        _save_file(REJECTED_FILE, [])

def _load_file(filepath):
    """Безопасно загружает данные из JSON файла."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_file(filepath, data):
    """Записывает данные в файл в формате UTF-8."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Ошибка сохранения]: Не удалось записать файл {filepath}. Причина: {e}")

def save_approved_vacancy(company, title, url, cover_letter="", description=""):
    """Добавляет новую одобренную ИИ вакансию в список."""
    vacancies = _load_file(APPROVED_FILE)
    new_vacancy = {
        "company": company,
        "title": title,
        "url": url,
        "description": description,
        "cover_letter": cover_letter
    }
    vacancies.append(new_vacancy)
    _save_file(APPROVED_FILE, vacancies)

def save_rejected_vacancy(company, title, url, reason=""):
    """Добавляет отклоненную вакансию в самоочищающийся журнал (макс 50 записей)."""
    vacancies = _load_file(REJECTED_FILE)
    new_vacancy = {
        "company": company,
        "title": title,
        "url": url,
        "reason": reason
    }
    vacancies.append(new_vacancy)
    # Самоочистка: держим только 50 последних записей, чтобы файл не разрастался
    if len(vacancies) > 50:
        vacancies = vacancies[-50:]
    _save_file(REJECTED_FILE, vacancies)

def get_all_approved():
    """Возвращает список всех сохраненных вакансий."""
    return _load_file(APPROVED_FILE)

def get_all_rejected():
    """Возвращает список всех отклоненных вакансий."""
    return _load_file(REJECTED_FILE)

def delete_vacancy_by_url(url):
    """Удаляет конкретную одобренную вакансию из списка по её ссылке."""
    vacancies = _load_file(APPROVED_FILE)
    vacancies = [v for v in vacancies if v.get('url') != url]
    _save_file(APPROVED_FILE, vacancies)

def delete_rejected_by_url(url):
    """Удаляет конкретную отклоненную вакансию по её ссылке."""
    vacancies = _load_file(REJECTED_FILE)
    vacancies = [v for v in vacancies if v.get('url') != url]
    _save_file(REJECTED_FILE, vacancies)

def clear_all_vacancies():
    """Полностью очищает базу данных одобренных."""
    _save_file(APPROVED_FILE, [])

def clear_all_rejected():
    """Полностью очищает базу данных отклоненных."""
    _save_file(REJECTED_FILE, [])