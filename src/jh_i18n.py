# jh_i18n.py — bilingual string store (EN default, RU optional)
_STRINGS = {
    "en": {
        # Main window
        "subtitle":              "Personal career automation assistant",
        "first_name_ph":         "First name (e.g. John)",
        "last_name_ph":          "Last name (e.g. Smith)",
        "resume_label":          "Your work experience and skills (for letter generation):",
        "btn_paste":             "Paste 📋",
        "btn_history":           "📂 History",
        "btn_settings":          "⚙ AI Settings",
        "filter_label":          "Primary automatic filter:",
        "cb_remote":             "Remote",
        "cb_office":             "Office",
        "cb_hybrid":             "Hybrid",
        "cb_no_rf":              "No local presence 🌐",
        "cb_location":           "No presence in:",
        "location_placeholder":  "e.g. Russia, Belarus",
        "status_loaded":         "● Configuration loaded successfully",
        "btn_start":             "START ASSISTANT",
        "btn_stop":              "STOP ASSISTANT",
        "btn_resume":            "▶  RESUME QUEUE",
        "btn_reset_queue":       "✕ CLEAR",
        "btn_results":           "📁 OPEN APPROVED VACANCIES",
        "status_paused":         "● Paused. {q} vacancies in queue — resume or clear?",
        # Settings window
        "settings_title":        "⚙ AI ENGINE SETTINGS",
        "settings_help":         "❔ Help",
        "provider_label":        "Active AI provider:",
        "key_label":             "Provider API Key:",
        "key_placeholder":       "Paste your access key...",
        "key_placeholder_local": "Local server (no key required)",
        "models_label":          "Priority cascade models:",
        "delay_label":           "API protection pause: {val} sec.",
        "strictness_label":      "AI Filter Strictness:",
        "strictness_mild":       "Mild",
        "strictness_balanced":   "Balanced",
        "strictness_strict":     "Strict",
        "letter_length_label":   "Cover Letter Length:",
        "letter_short":          "Short",
        "letter_balanced":       "Balanced",
        "letter_detailed":       "Detailed",
        "cb_notifications":      "Desktop notifications on queue complete & errors",
        "btn_save":              "SAVE AND CLOSE",
        "status_saved":          "● Configuration saved successfully",
        # API Help window
        "help_win_title":        "How to get a free API key?",
        "help_title":            "🔑 Free Gemini API key in 1 minute",
        "help_text": (
            "For the Gemini provider you can get an official\n"
            "high-speed API key absolutely free.\n\n"
            "1. Follow the link to Google AI Studio.\n"
            "2. Click the 'Get API Key' button.\n"
            "3. Copy and paste it into Job Hunter AI settings."
        ),
        "help_btn":              "Get key at Google AI Studio 🌐",
        # Warning window
        "warn_win_title":        "Local models — performance requirements",
        "warn_title":            "⚠ Local model requirements",
        "warn_text": (
            "You selected a local model (Ollama / LM Studio).\n\n"
            "Vacancies are processed one at a time — the queue is sequential.\n"
            "The delay between vacancies is configurable to your preference.\n\n"
            "However, cover letter generation runs on your PC and must finish\n"
            "within the timeout. Slow models will time out and the vacancy\n"
            "will not be saved.\n\n"
            "Tips:\n"
            "• Lightweight models (3B–8B) are strongly recommended.\n"
            "• Close heavy apps to free up RAM and GPU memory.\n"
            "• Make sure Ollama / LM Studio is running before you start."
        ),
        "warn_dont_show":        "Don't show again",
        "warn_ok":               "Got it",
        # Status / runtime messages
        "status_key_required":   "● Enter API key for provider {provider}",
        "status_active":         "● Assistant active. Waiting for vacancies...",
        "status_stopped":        "● Assistant stopped",
        "status_queue":          "● [{done} done] Pausing {sec}s · {q} in queue",
        "status_analyzing":      "● AI is analyzing the incoming vacancy...",
        "status_approved":       "✓ APPROVED: {title} at {company}!",
        "status_rejected":       "✕ Rejected by AI: {title} at {company} (reason in results)",
        "status_error":          "⚠ AI error: {msg}",
        "status_proc_error":     "⚠ Processing failed: {msg}",
        "status_server_fail":    "⚠ Web server failed on port {port}. Close other copies of the app.",
        "status_queue_added":    "● Incoming vacancy added to queue (total: {q})",
        "status_duplicate_queue": "⚠ Duplicate: vacancy already in the processing queue (skipped)",
        "status_duplicate_db":   "⚠ Already processed before — found in results (skipped)",
        "status_local_check":    "● Checking local server {provider}...",
        "status_server_down":    "⚠ {provider} server offline — check Ollama / LM Studio",
        # Error dialogs
        "err_start_title":       "Launch error",
        "err_key_msg":           "Please enter your API Key for provider {provider} in the 'AI Settings' window.",
        "err_name_msg":          "Please enter your first name (it is used for letter generation).",
        "err_no_model_msg":      "No models selected for {provider}. Enable at least one model in AI Settings.",
        "err_server_msg":        "{provider} server is not running. Please start Ollama / LM Studio first.",
        # Resume history window
        "history_win_title":     "Resume History",
        "history_save_name_ph":  "Name for this resume...",
        "history_btn_save":      "Save current",
        "history_btn_load":      "Load",
        "history_btn_delete":    "✕",
        "history_empty":         "No saved resumes yet.",
        "history_overwrite_q":   "'{name}' already exists. Overwrite?",
        "history_name_empty":    "Please enter a name for the resume.",
        "notif_queue_done":      "Queue complete: {approved} approved, {rejected} rejected",
        "notif_error_body":      "Error processing vacancy. Check AI settings.",
        # Results window
        "results_title":         "AI Analysis Results",
        "monitoring":            "AI Monitoring",
        "btn_clear":             "\U0001f5d1️ Clear list",
        "tab_approved":          "AI Approved ({n}) \U0001f44d",
        "tab_rejected":          "AI Rejected ({n}) ✕",
        "empty_approved":        "No approved vacancies yet.",
        "empty_rejected":        "Rejection log is empty.",
        "clear_approved_q":      "Are you sure you want to permanently delete ALL approved vacancies?",
        "clear_rejected_q":      "Are you sure you want to clear the entire rejection log?",
        "clear_title":           "Clear database",
        "btn_letter":            "✍️ Letter",
        "btn_apply":             "\U0001f680 Apply",
        "btn_anyway":            "\U0001f517 Apply anyway",
        "btn_delete_rej":        "Remove from history ✕",
        "no_link":               "The vacancy link is missing.",
        "link_error":            "Could not open link: {e}",
        "letter_win_title":      "Cover Letter",
        "btn_copy":              "\U0001f4cb Copy letter",
        "copied_ok_text":        "Copied! ✓",
        "btn_copy_orig":         "\U0001f4cb Copy letter",
        # App-generated reject reasons
        "reject_remote":         "Remote work is disabled in app settings.",
        "reject_office":         "Office work is disabled in app settings.",
        "reject_hybrid":         "Hybrid work is disabled in app settings.",
        "reject_local":          "Requires physical presence at the job location.",
        "reject_geo_excluded":   "Your location is excluded from this vacancy's geography.",
        "reject_geo_required":   "This vacancy requires presence in a specific region.",
        # PDF resume import
        "btn_pdf_import":        "PDF",
        "pdf_processing":        "● Distilling resume from PDF...",
        "pdf_error_damaged":     "PDF file is damaged or unreadable.",
        "pdf_error_no_text":     "No readable text found in PDF. Use a text-based PDF (not a scan).",
        "pdf_error_ai":          "AI distillation failed: {msg}",
    },
    "ru": {
        # Main window
        "subtitle":              "Персональный ассистент по автоматизации карьеры",
        "first_name_ph":         "Имя (например, Иван)",
        "last_name_ph":          "Фамилия (например, Иванов)",
        "resume_label":          "Ваш опыт работы и навыки (для генерации писем):",
        "btn_paste":             "Вставить \U0001f4cb",
        "btn_history":           "📂 История",
        "btn_settings":          "⚙ Настройки ИИ",
        "filter_label":          "Первичный автоматический отсев:",
        "cb_remote":             "Удаленка",
        "cb_office":             "Офис",
        "cb_hybrid":             "Гибрид",
        "cb_no_rf":              "Без локальной привязки \U0001f310",
        "cb_location":           "Без присутствия в:",
        "location_placeholder":  "напр. Россия, Беларусь",
        "status_loaded":         "● Конфигурация успешно загружена",
        "btn_start":             "ЗАПУСТИТЬ АССИСТЕНТА",
        "btn_stop":              "ОТКЛЮЧИТЬ АССИСТЕНТА",
        "btn_resume":            "▶  ПРОДОЛЖИТЬ ОЧЕРЕДЬ",
        "btn_reset_queue":       "✕ СБРОС",
        "btn_results":           "\U0001f4c1 ОТКРЫТЬ ОДОБРЕННЫЕ ВАКАНСИИ (ОТОБРАНО)",
        "status_paused":         "● Пауза. В очереди {q} вакансий — продолжить или сбросить?",
        # Settings window
        "settings_title":        "⚙ НАСТРОЙКИ AI ENGINE",
        "settings_help":         "❔ Помощь",
        "provider_label":        "Активный провайдер ИИ:",
        "key_label":             "API Ключ провайдера:",
        "key_placeholder":       "Вставьте ключ доступа...",
        "key_placeholder_local": "Локальный сервер (ключ не требуется)",
        "models_label":          "Приоритетные модели каскада:",
        "delay_label":           "Защитная пауза API: {val} сек.",
        "strictness_label":      "Строгость фильтра ИИ:",
        "strictness_mild":       "Мягкий",
        "strictness_balanced":   "Баланс",
        "strictness_strict":     "Строгий",
        "letter_length_label":   "Длина письма:",
        "letter_short":          "Короткое",
        "letter_balanced":       "Сбалансированное",
        "letter_detailed":       "Подробное",
        "cb_notifications":      "Уведомление при завершении очереди и ошибках",
        "btn_save":              "СОХРАНИТЬ И ЗАКРЫТЬ",
        "status_saved":          "● Конфигурация успешно сохранена",
        # API Help window
        "help_win_title":        "Где взять бесплатный API ключ?",
        "help_title":            "\U0001f511 API-ключ Gemini бесплатно за 1 минуту",
        "help_text": (
            "Для провайдера Gemini вы можете получить официальный\n"
            "высокоскоростной API-ключ абсолютно бесплатно.\n\n"
            "1. Перейдите по ссылке в Google AI Studio.\n"
            "2. Нажмите кнопку 'Get API Key'.\n"
            "3. Скопируйте и вставьте в настройки Job Hunter AI."
        ),
        "help_btn":              "Получить ключ в Google AI Studio \U0001f310",
        # Warning window
        "warn_win_title":        "Локальные модели — требования к производительности",
        "warn_title":            "⚠ Требования к локальным моделям",
        "warn_text": (
            "Вы выбрали локальную модель (Ollama / LM Studio).\n\n"
            "Вакансии обрабатываются последовательно — одна за другой.\n"
            "Задержка между вакансиями настраивается по вашему усмотрению.\n\n"
            "Однако генерация сопроводительного письма идёт на вашем ПК\n"
            "и должна уложиться в таймаут. Медленная модель не успеет,\n"
            "и вакансия не будет сохранена.\n\n"
            "Советы:\n"
            "• Рекомендуются компактные модели (3B–8B).\n"
            "• Закройте тяжёлые приложения, освободите оперативную память.\n"
            "• Запустите Ollama / LM Studio до старта ассистента."
        ),
        "warn_dont_show":        "Больше не показывать",
        "warn_ok":               "Понятно",
        # Status / runtime messages
        "status_key_required":   "● Введите API-ключ для провайдера {provider}",
        "status_active":         "● Ассистент активен. Ожидание вакансий...",
        "status_stopped":        "● Ассистент отключен",
        "status_queue":          "● [{done} обраб.] Пауза {sec}с · в очереди: {q}",
        "status_analyzing":      "● ИИ анализирует прилетевшую вакансию...",
        "status_approved":       "✓ ОДОБРЕНО: {title} в {company}!",
        "status_rejected":       "✕ Отклонено ИИ: {title} в {company} (причина в результатах)",
        "status_error":          "⚠ Сбой ИИ: {msg}",
        "status_proc_error":     "⚠ Сбой обработки: {msg}",
        "status_server_fail":    "⚠ Сбой веб-сервера на порту {port}. Закройте другие копии программы.",
        "status_queue_added":    "● Входящая вакансия добавлена в очередь (всего: {q})",
        "status_duplicate_queue": "⚠ Дубликат: вакансия уже есть в очереди обработки (пропущено)",
        "status_duplicate_db":   "⚠ Уже обрабатывалась ранее — найдена в результатах (пропущено)",
        "status_local_check":    "● Проверка локального сервера {provider}...",
        "status_server_down":    "⚠ Сервер {provider} недоступен — проверьте Ollama / LM Studio",
        # Error dialogs
        "err_start_title":       "Ошибка запуска",
        "err_key_msg":           "Пожалуйста, введите ваш API Ключ для провайдера {provider} в окне 'Настройки ИИ'.",
        "err_name_msg":          "Пожалуйста, укажите ваше имя (оно используется для генерации писем).",
        "err_no_model_msg":      "Не выбрана ни одна модель для {provider}. Включите хотя бы одну в настройках ИИ.",
        "err_server_msg":        "Сервер {provider} не запущен. Запустите Ollama / LM Studio перед стартом.",
        # Resume history window
        "history_win_title":     "История резюме",
        "history_save_name_ph":  "Имя резюме...",
        "history_btn_save":      "Сохранить текущее",
        "history_btn_load":      "Загрузить",
        "history_btn_delete":    "✕",
        "history_empty":         "Сохранённых резюме нет.",
        "history_overwrite_q":   "'{name}' уже существует. Перезаписать?",
        "history_name_empty":    "Введите имя резюме.",
        "notif_queue_done":      "Очередь обработана: {approved} одобрено, {rejected} отклонено",
        "notif_error_body":      "Ошибка обработки вакансии. Проверьте настройки AI.",
        # Results window
        "results_title":         "Результаты анализа ИИ",
        "monitoring":            "Мониторинг ИИ",
        "btn_clear":             "\U0001f5d1️ Очистить список",
        "tab_approved":          "Одобренные ИИ ({n}) \U0001f44d",
        "tab_rejected":          "Отклоненные ИИ ({n}) ✕",
        "empty_approved":        "Список одобренных вакансий пока пуст.",
        "empty_rejected":        "Журнал отклонений пуст.",
        "clear_approved_q":      "Вы уверены, что хотите безвозвратно удалить ВСЕ одобренные вакансии?",
        "clear_rejected_q":      "Вы уверены, что хотите очистить весь журнал отклонённых вакансий?",
        "clear_title":           "Очистка базы данных",
        "btn_letter":            "✍️ Письмо",
        "btn_apply":             "\U0001f680 Откликнуться",
        "btn_anyway":            "\U0001f517 Всё равно откликнуться",
        "btn_delete_rej":        "Удалить из истории ✕",
        "no_link":               "Ссылка на вакансию отсутствует.",
        "link_error":            "Не удалось открыть ссылку: {e}",
        "letter_win_title":      "Сопроводительное письмо",
        "btn_copy":              "\U0001f4cb Скопировать письмо",
        "copied_ok_text":        "Скопировано! ✓",
        "btn_copy_orig":         "\U0001f4cb Скопировать письмо",
        # App-generated reject reasons
        "reject_remote":         "Удаленная работа отключена в настройках приложения.",
        "reject_office":         "Работа в офисе отключена в настройках приложения.",
        "reject_hybrid":         "Гибридная работа отключена в настройках приложения.",
        "reject_local":          "Требуется физическое присутствие на месте работы.",
        "reject_geo_excluded":   "Ваша локация исключена из географии этой вакансии.",
        "reject_geo_required":   "Вакансия требует присутствия в определённом регионе.",
        # PDF resume import
        "btn_pdf_import":        "PDF",
        "pdf_processing":        "● Дистилляция резюме из PDF...",
        "pdf_error_damaged":     "Файл PDF повреждён или нечитаем.",
        "pdf_error_no_text":     "В PDF не найден читаемый текст. Используйте текстовый PDF (не скан).",
        "pdf_error_ai":          "Сбой дистилляции ИИ: {msg}",
    },
}

_current_lang: str = "en"


def set_language(lang: str) -> None:
    global _current_lang
    if lang in _STRINGS:
        _current_lang = lang


def get_language() -> str:
    return _current_lang


def tr(key: str, **kwargs) -> str:
    text = _STRINGS.get(_current_lang, {}).get(key) or _STRINGS["en"].get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text
