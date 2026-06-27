# main_app.py
import os
import sys
import json
import threading
import queue
import time
import customtkinter as ctk
from tkinter import messagebox
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image, ImageTk
import ai_engine
import storage_manager
import results_ui

# =====================================================================
# НАСТРОЙКА DPI И СИСТЕМНОГО ОКРУЖЕНИЯ Windows
# =====================================================================
try:
    import ctypes
    # Включаем DPI-Awareness, чтобы шрифты на High-DPI экранах (2K/4K) были идеально четкими
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Настройки путей к конфигурации
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Job Hunter AI')
os.makedirs(APPDATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")
ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
LOGO_PNG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

# Инициализируем локальную БД
storage_manager.init_db()

# Цветовая неоновая космическая палитра (согласована с results_ui.py)
COLOR_BG_DARK = "#090D14"       # Мягкий глубокий темный космос
COLOR_CARD_BG = "#111622"       # Спокойный сине-серый фон карточек
COLOR_INPUT_BG = "#171D2C"      # Пространство полей ввода / неактивных кнопок
COLOR_CYAN_NEON = "#00D8C6"     # Благородный мягкий циан (лого/успех)
COLOR_CYAN_HOVER = "#00A193"    # Глубокий бирюзовый (hover)
COLOR_GOLD = "#E2A33C"          # Теплое золото туманности (ожидание/актив)
COLOR_GOLD_HOVER = "#B3802F"    # Мягкий янтарный (hover)
COLOR_RED = "#D24B4B"           # Приглушенный красный (опасность/удаление)
COLOR_RED_HOVER = "#A83C3C"     # Глубокий вишневый (hover)
COLOR_TEXT_MUTED = "#828D9A"     # Пыльно-серый текст
COLOR_TEXT_LIGHT = "#E9EDF0"     # Комфортный белый звездный текст

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ИНТЕРФЕЙСА
# =====================================================================
def force_dark_title_bar(window):
    """Принудительно перекрашивает заголовок окна Windows в темный цвет"""
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if hwnd == 0: hwnd = window.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception:
        pass

def center_window(window, width, height, parent=None):
    """
    Абсолютно безопасная функция центрирования окон для High-DPI экранов.
    Использует прозрачность вместо withdraw для предотвращения сбоя инициализации handles.
    """
    try:
        window.attributes("-alpha", 0.0)
    except Exception:
        pass
    
    def _apply_centered_position():
        if not window.winfo_exists():
            return
        try:
            window.update_idletasks()
            
            # Безопасное получение масштаба через приватный метод инстанса CTk
            try:
                scaling = window._get_window_scaling()
            except Exception:
                scaling = 1.0

            scaled_width = int(width * scaling)
            scaled_height = int(height * scaling)
            
            if parent and parent.winfo_exists():
                # Находим координаты родительского окна (уже масштабированы системой)
                parent_x = parent.winfo_x()
                parent_y = parent.winfo_y()
                parent_w = parent.winfo_width()
                parent_h = parent.winfo_height()
                
                x = parent_x + (parent_w - scaled_width) // 2
                y = parent_y + (parent_h - scaled_height) // 2
            else:
                # Размеры экрана монитора в системных координатах
                screen_width = window.winfo_screenwidth()
                screen_height = window.winfo_screenheight()
                
                x = (screen_width - scaled_width) // 2
                y = (screen_height - scaled_height) // 2
            
            # Защита от улета за границы экрана
            x = max(0, int(x))
            y = max(0, int(y))
            
            window.geometry(f"{width}x{height}+{x}+{y}")
        except Exception as e:
            print(f"[Резервное центрирование]: {e}")
            window.geometry(f"{width}x{height}")
        finally:
            # Блок гарантирует, что окно обязательно станет видимым на экране в любом случае!
            try:
                window.attributes("-alpha", 1.0)
                window.deiconify()
            except Exception:
                pass
        
    window.after(100, _apply_centered_position)

def bind_russian_hotkeys(widget):
    """
    Аппаратно-независимая обработка горячих клавиш (Ctrl+C, Ctrl+V, Ctrl+A, Ctrl+X)
    для русской и английской раскладок клавиатуры на уровне базовых виджетов Windows/Linux.
    """
    target = widget
    if hasattr(widget, "_entry"):
        target = widget._entry
    elif hasattr(widget, "_textbox"):
        target = widget._textbox

    def handle_control_keys(event):
        key = event.keysym.lower()
        keycode = event.keycode
        
        # Вставка (Ctrl+V) -> код клавиши 86 на Windows
        if keycode == 86 or key in ('v', 'cyrillic_em'):
            try:
                text = event.widget.clipboard_get()
                try:
                    if event.widget.tag_ranges("sel"):
                        event.widget.delete("sel.first", "sel.last")
                except Exception:
                    try:
                        if event.widget.selection_present():
                            event.widget.delete("sel.first", "sel.last")
                    except Exception:
                        pass
                event.widget.insert("insert", text)
            except Exception:
                pass
            return "break"
            
        # Копирование (Ctrl+C) -> код клавиши 67 на Windows
        elif keycode == 67 or key in ('c', 'cyrillic_es'):
            try:
                selected_text = None
                try:
                    selected_text = event.widget.get("sel.first", "sel.last")
                except Exception:
                    try:
                        selected_text = event.widget.selection_get()
                    except Exception:
                        pass
                if selected_text:
                    event.widget.clipboard_clear()
                    event.widget.clipboard_append(selected_text)
            except Exception:
                pass
            return "break"
            
        # Выделить все (Ctrl+A) -> код клавиши 65 на Windows
        elif keycode == 65 or key in ('a', 'cyrillic_ef'):
            try:
                if hasattr(event.widget, "tag_add"):
                    event.widget.tag_add("sel", "1.0", "end-1c")
                    event.widget.mark_set("insert", "1.0")
                elif hasattr(event.widget, "select_range"):
                    event.widget.select_range(0, "end")
                    event.widget.icursor("end")
            except Exception:
                pass
            return "break"
            
        # Вырезать (Ctrl+X) -> код клавиши 88 на Windows
        elif keycode == 88 or key in ('x', 'cyrillic_che'):
            try:
                selected_text = None
                try:
                    selected_text = event.widget.get("sel.first", "sel.last")
                    if selected_text:
                        event.widget.clipboard_clear()
                        event.widget.clipboard_append(selected_text)
                        event.widget.delete("sel.first", "sel.last")
                except Exception:
                    try:
                        selected_text = event.widget.selection_get()
                        if selected_text:
                            event.widget.clipboard_clear()
                            event.widget.clipboard_append(selected_text)
                            event.widget.delete("sel.first", "sel.last")
                    except Exception:
                        pass
            except Exception:
                pass
            return "break"

    try:
        target.bind("<Control-KeyPress>", handle_control_keys)
    except Exception as e:
        print(f"[Ошибка привязки клавиш]: {e}")

# =====================================================================
# ФОНОВЫЙ FLASK СЕРВЕР (ПРИЕМ ДАННЫХ ИЗ РАСШИРЕНИЯ)
# =====================================================================
flask_app = Flask(__name__)
CORS(flask_app)
app_instance = None  # Ссылка на экземпляр GUI для вывода логов и статусов

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    global app_instance
    if not app_instance or not app_instance.is_active:
        return jsonify({"status": "ignored", "reason": "Assistant is offline"}), 200
        
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "reason": "No data received"}), 400
            
        # Помещаем входящую вакансию в очередь обработки
        app_instance.enqueue_vacancy(data)
        return jsonify({"status": "received", "queue_position": app_instance.vacancy_queue.qsize()}), 200
    except Exception as e:
        return jsonify({"status": "error", "reason": str(e)}), 500

# =====================================================================
# ГЛАВНЫЙ ИНТЕРФЕЙС ПРИЛОЖЕНИЯ
# =====================================================================
class JobHunterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        global app_instance
        app_instance = self
        
        self.is_active = False
        self.server_started = False
        
        # Потокобезопасная очередь для вакансий
        self.vacancy_queue = queue.Queue()
        self.worker_thread = None
        self.stop_worker_event = threading.Event()
        
        self.title("Job Hunter AI v1.1")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_DARK)
        
        # Настройка глобального внешнего вида CustomTkinter под неоновый стиль
        ctk.set_appearance_mode("dark")
        
        # Центрируем главное окно
        center_window(self, 680, 770)
        force_dark_title_bar(self)
        
        # Установка иконки
        try:
            if os.path.exists(ICON_PATH):
                self.iconbitmap(ICON_PATH)
        except Exception:
            pass

        # Отрисовка UI
        self.setup_ui()
        self.load_config()

    def load_and_resize_logo(self, height_pixels):
        """Загружает логотип и масштабирует его в зависимости от DPI экрана"""
        try:
            # Получение коэффициента масштабирования DPI
            try:
                scaling = self._get_window_scaling()
            except Exception:
                scaling = 1.0

            # Вычисление физических размеров для загрузки
            target_height = int(height_pixels * scaling)
            
            logo_img = None
            if os.path.exists(LOGO_PNG_PATH):
                logo_img = Image.open(LOGO_PNG_PATH)
            elif os.path.exists(ICON_PATH):
                logo_img = Image.open(ICON_PATH)

            if logo_img:
                # Сохраняем соотношение сторон
                aspect_ratio = logo_img.width / logo_img.height
                target_width = int(target_height * aspect_ratio)
                
                # Масштабирование без размытия с использованием High-Quality ресайза
                logo_img = logo_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # Возвращаем CTkImage с учетом исходного DPI для CustomTkinter
                return ctk.CTkImage(
                    light_image=logo_img,
                    dark_image=logo_img,
                    size=(int(target_width / scaling), int(target_height / scaling))
                )
        except Exception as e:
            print(f"[Ошибка загрузки логотипа]: {e}")
        return None

    def setup_ui(self):
        """Создает элементы управления в главном окне"""
        # Шапка с логотипом и названием
        header_container = ctk.CTkFrame(self, fg_color="transparent")
        header_container.pack(pady=(20, 5))
        
        logo_image = self.load_and_resize_logo(38)
        
        if logo_image:
            logo_lbl = ctk.CTkLabel(header_container, image=logo_image, text="")
            logo_lbl.pack(side="left", padx=(0, 12))
            
        title_lbl = ctk.CTkLabel(
            header_container, 
            text="JOB HUNTER AI", 
            font=("Arial", 24, "bold"), 
            text_color=COLOR_CYAN_NEON
        )
        title_lbl.pack(side="left")
        
        subtitle_lbl = ctk.CTkLabel(
            self, 
            text="Персональный ассистент по автоматизации карьеры", 
            font=("Arial", 12), 
            text_color=COLOR_TEXT_MUTED
        )
        subtitle_lbl.pack(pady=(0, 20))

        # Поля ввода имени и фамилии в одну строчку
        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.pack(pady=10, padx=30, fill="x")
        
        self.first_name_input = ctk.CTkEntry(
            name_frame, 
            placeholder_text="Имя (например, Иван)", 
            height=45, 
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text_color=COLOR_TEXT_MUTED
        )
        self.first_name_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        bind_russian_hotkeys(self.first_name_input)
        
        self.last_name_input = ctk.CTkEntry(
            name_frame, 
            placeholder_text="Фамилия (например, Иванов)", 
            height=45, 
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text_color=COLOR_TEXT_MUTED
        )
        self.last_name_input.pack(side="right", fill="x", expand=True, padx=(10, 0))
        bind_russian_hotkeys(self.last_name_input)

        # Опыт работы и навыки (Резюме) - Заголовок и кнопка вставки
        resume_header_frame = ctk.CTkFrame(self, fg_color="transparent")
        resume_header_frame.pack(anchor="w", padx=30, pady=(15, 5), fill="x")
        
        resume_lbl = ctk.CTkLabel(
            resume_header_frame, 
            text="Ваш опыт работы и навыки (для генерации писем):", 
            font=("Arial", 13, "bold"), 
            text_color=COLOR_TEXT_LIGHT
        )
        resume_lbl.pack(side="left")
        
        def paste_to_resume():
            try:
                clipboard_text = self.clipboard_get()
                self.resume_input.delete("0.0", "end")
                self.resume_input.insert("0.0", clipboard_text.strip())
            except Exception:
                pass

        btn_paste_resume = ctk.CTkButton(
            resume_header_frame, 
            text="Вставить 📋", 
            width=95, 
            height=26, 
            font=("Arial", 11, "bold"), 
            fg_color=COLOR_CYAN_NEON, 
            hover_color=COLOR_CYAN_HOVER, 
            text_color=COLOR_BG_DARK,
            command=paste_to_resume
        )
        btn_paste_resume.pack(side="right")
        
        self.resume_input = ctk.CTkTextbox(
            self, 
            height=140, 
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            border_width=1,
            text_color=COLOR_TEXT_LIGHT
        )
        self.resume_input.pack(pady=5, padx=30, fill="x")
        bind_russian_hotkeys(self.resume_input)

        # Лицензия / API Ключ Gemini
        key_lbl = ctk.CTkLabel(
            self, 
            text="Лицензия и ИИ-доступ:", 
            font=("Arial", 13, "bold"), 
            text_color=COLOR_TEXT_LIGHT
        )
        key_lbl.pack(anchor="w", padx=30, pady=(15, 5))
        
        key_frame = ctk.CTkFrame(self, fg_color="transparent")
        key_frame.pack(pady=5, padx=30, fill="x")
        
        self.api_key_input = ctk.CTkEntry(
            key_frame, 
            placeholder_text="Введите ваш Gemini API Key (начинается с AIza...)", 
            height=45, 
            fg_color=COLOR_INPUT_BG, 
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text_color=COLOR_TEXT_MUTED,
            show="*"
        )
        self.api_key_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        bind_russian_hotkeys(self.api_key_input)
        
        btn_paste = ctk.CTkButton(
            key_frame, 
            text="Вставить 📋", 
            width=100, 
            height=45, 
            fg_color=COLOR_CYAN_NEON, 
            hover_color=COLOR_CYAN_HOVER, 
            text_color=COLOR_BG_DARK,
            font=("Arial", 12, "bold"),
            command=self.paste_key
        )
        btn_paste.pack(side="left", padx=5)
        
        btn_help = ctk.CTkButton(
            key_frame, 
            text="Помощь ❓", 
            width=100, 
            height=45, 
            fg_color=COLOR_CARD_BG, 
            hover_color=COLOR_INPUT_BG, 
            text_color=COLOR_TEXT_LIGHT,
            font=("Arial", 12, "bold"),
            command=self.show_help
        )
        btn_help.pack(side="right", padx=(5, 0))

        # Фильтры отсева вакансий
        filter_lbl = ctk.CTkLabel(
            self, 
            text="Первичный автоматический отсев:", 
            font=("Arial", 13, "bold"), 
            text_color=COLOR_TEXT_LIGHT
        )
        filter_lbl.pack(anchor="w", padx=30, pady=(15, 5))
        
        filter_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, height=60, corner_radius=8)
        filter_frame.pack(pady=5, padx=30, fill="x")
        
        self.cb_remote = ctk.CTkCheckBox(
            filter_frame, 
            text="Удаленка", 
            text_color=COLOR_TEXT_LIGHT, 
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_INPUT_BG
        )
        self.cb_remote.pack(side="left", padx=15, pady=15)
        self.cb_remote.select()
        
        self.cb_office = ctk.CTkCheckBox(
            filter_frame, 
            text="Офис", 
            text_color=COLOR_TEXT_LIGHT, 
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_INPUT_BG
        )
        self.cb_office.pack(side="left", padx=15, pady=15)
        
        self.cb_hybrid = ctk.CTkCheckBox(
            filter_frame, 
            text="Гибрид", 
            text_color=COLOR_TEXT_LIGHT, 
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_INPUT_BG
        )
        self.cb_hybrid.pack(side="left", padx=15, pady=15)
        
        self.cb_no_rf = ctk.CTkCheckBox(
            filter_frame, 
            text="Без привязки к РФ 🌐", 
            text_color=COLOR_TEXT_LIGHT, 
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_INPUT_BG
        )
        self.cb_no_rf.pack(side="right", padx=15, pady=15)
        self.cb_no_rf.select()

        # Статус-бар логов и состояния приложения (с автоматическим переносом длинных строк)
        self.status_lbl = ctk.CTkLabel(
            self, 
            text="● Настройки профиля успешно загружены", 
            font=("Arial", 12, "bold"), 
            text_color=COLOR_CYAN_NEON, 
            wraplength=600
        )
        self.status_lbl.pack(pady=10)

        # Главные кнопки управления
        self.btn_toggle = ctk.CTkButton(
            self, 
            text="ЗАПУСТИТЬ АССИСТЕНТА", 
            font=("Arial", 15, "bold"), 
            fg_color=COLOR_CYAN_NEON, 
            hover_color=COLOR_CYAN_HOVER, 
            text_color=COLOR_BG_DARK,
            height=50, 
            command=self.toggle_assistant
        )
        self.btn_toggle.pack(pady=5, padx=30, fill="x")
        
        btn_open_results = ctk.CTkButton(
            self, 
            text="📁 ОТКРЫТЬ ОДОБРЕННЫЕ ВАКАНСИИ (ОТОБРАНО)", 
            font=("Arial", 13, "bold"), 
            fg_color=COLOR_GOLD, 
            hover_color=COLOR_GOLD_HOVER, 
            text_color=COLOR_BG_DARK,
            height=45, 
            command=self.open_results
        )
        btn_open_results.pack(pady=(5, 20), padx=30, fill="x")

    # =====================================================================
    # ЛОГИКА И СЕРВИСНЫЕ МЕТОДЫ ПРИЛОЖЕНИЯ
    # =====================================================================
    def paste_key(self):
        try:
            clipboard_text = self.clipboard_get()
            self.api_key_input.delete(0, "end")
            self.api_key_input.insert(0, clipboard_text.strip())
        except Exception:
            pass

    def show_help(self):
        messagebox.showinfo(
            "Инструкция: Получение API Key",
            "Для работы ИИ-ассистента требуется персональный бесплатный ключ Gemini API.\n\n"
            "Как получить:\n"
            "1. Перейдите на сайт Google AI Studio (aistudio.google.com)\n"
            "2. Войдите под своим Google-аккаунтом\n"
            "3. Нажмите кнопку 'Get API Key', а затем 'Create API Key'\n"
            "4. Скопируйте созданный ключ (он начинается на AIza...) и вставьте его в это поле."
        )

    def load_config(self):
        """Загружает сохраненные настройки пользователя при запуске"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    self.first_name_input.insert(0, config.get("first_name", ""))
                    self.last_name_input.insert(0, config.get("last_name", ""))
                    self.resume_input.insert("0.0", config.get("resume", ""))
                    self.api_key_input.insert(0, config.get("api_key", ""))
                    
                    if not config.get("filter_remote", True): self.cb_remote.deselect()
                    if config.get("filter_office", False): self.cb_office.select()
                    if config.get("filter_hybrid", False): self.cb_hybrid.select()
                    if not config.get("filter_no_rf", True): self.cb_no_rf.deselect()
            except Exception:
                pass

    def save_current_config(self):
        """Сохраняет текущие введенные настройки в AppData"""
        config = {
            "first_name": self.first_name_input.get().strip(),
            "last_name": self.last_name_input.get().strip(),
            "resume": self.resume_input.get("0.0", "end-1c").strip(),
            "api_key": self.api_key_input.get().strip(),
            "filter_remote": bool(self.cb_remote.get()),
            "filter_office": bool(self.cb_office.get()),
            "filter_hybrid": bool(self.cb_hybrid.get()),
            "filter_no_rf": bool(self.cb_no_rf.get())
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Ошибка сохранения конфига]: {e}")

    def toggle_assistant(self):
        """Включает/выключает прием вебхуков и работу ИИ"""
        if not self.is_active:
            # Валидация перед запуском
            api_key = self.api_key_input.get().strip()
            first_name = self.first_name_input.get().strip()
            
            if not api_key:
                messagebox.showerror("Ошибка запуска", "Пожалуйста, введите ваш Gemini API Ключ.")
                return
            if not first_name:
                messagebox.showerror("Ошибка запуска", "Пожалуйста, укажите ваше имя (оно используется для генерации писем).")
                return

            self.save_current_config()
            self.is_active = True
            
            # Меняем визуальный статус кнопки на отключение
            self.btn_toggle.configure(text="ОТКЛЮЧИТЬ АССИСТЕНТА", fg_color=COLOR_RED, hover_color=COLOR_RED_HOVER, text_color=COLOR_TEXT_LIGHT)
            self.status_lbl.configure(text="● Ассистент активен. Ожидание вакансий из браузера...", text_color=COLOR_CYAN_NEON)
            
            # Сбрасываем и инициализируем потокобезопасную очередь
            while not self.vacancy_queue.empty():
                try:
                    self.vacancy_queue.get_nowait()
                except queue.Empty:
                    break
            
            self.stop_worker_event.clear()
            self.worker_thread = threading.Thread(target=self.queue_worker_loop, daemon=True)
            self.worker_thread.start()
            
            # Запуск Flask-сервера (только один раз при первом клике)
            if not self.server_started:
                self.server_started = True
                threading.Thread(target=self.run_flask_server, daemon=True).start()
        else:
            self.is_active = False
            self.stop_worker_event.set()
            self.btn_toggle.configure(text="ЗАПУСТИТЬ АССИСТЕНТА", fg_color=COLOR_CYAN_NEON, hover_color=COLOR_CYAN_HOVER, text_color=COLOR_BG_DARK)
            self.status_lbl.configure(text="● Ассистент отключен", text_color=COLOR_RED)

    def run_flask_server(self):
        """Запускает Flask-сервер на стандартном порту вебхуков расширения"""
        try:
            flask_app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
        except Exception as e:
            print(f"[Flask Сбой]: {e}")

    def update_status(self, text, color):
        """Безопасное обновление статуса на главном экране из фоновых потоков"""
        self.after(0, lambda: self.status_lbl.configure(text=text, text_color=color))

    def enqueue_vacancy(self, data):
        """Добавляет входящую вакансию в очередь и обновляет счетчик"""
        self.vacancy_queue.put(data)
        q_size = self.vacancy_queue.qsize()
        self.update_status(f"● Входящая вакансия добавлена в очередь (всего в очереди: {q_size})", COLOR_GOLD)

    def queue_worker_loop(self):
        """Фоновый непрерывный цикл, разгребающий очередь с задержкой в 15 секунд перед ИИ"""
        while not self.stop_worker_event.is_set():
            try:
                # Получаем вакансию с таймаутом в 1 секунду, чтобы регулярно проверять stop_worker_event
                vacancy_data = self.vacancy_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Запускаем защитный таймер 15 секунд перед ПЕРВЫМ ИИ отсевом
            for remaining in range(15, 0, -1):
                if self.stop_worker_event.is_set():
                    return
                q_size = self.vacancy_queue.qsize() + 1 # Включая текущую вакансию
                self.update_status(
                    f"● Пауза {remaining} сек для защиты лимитов API (в очереди: {q_size})", 
                    COLOR_GOLD
                )
                time.sleep(1)

            # Переходим к обработке вакансии
            if not self.stop_worker_event.is_set():
                self.process_incoming_vacancy(vacancy_data)
                self.vacancy_queue.task_done()

    def process_incoming_vacancy(self, vacancy_data):
        """Обработка одной вакансии через ИИ-движок"""
        self.update_status("● ИИ анализирует прилетевшую вакансию...", COLOR_GOLD)
        
        config = {
            "api_key": self.api_key_input.get().strip(),
            "first_name": self.first_name_input.get().strip(),
            "resume": self.resume_input.get("0.0", "end-1c").strip(),
            "filter_remote": bool(self.cb_remote.get()),
            "filter_office": bool(self.cb_office.get()),
            "filter_hybrid": bool(self.cb_hybrid.get()),
            "filter_no_rf": bool(self.cb_no_rf.get())
        }

        try:
            # Вызываем наш двухстадийный ИИ-фильтр
            status, result_text, extracted_info = ai_engine.analyze_and_generate(vacancy_data, config)
            
            company = extracted_info.get("company", vacancy_data.get("company", "Не указана"))
            title = extracted_info.get("title", vacancy_data.get("title", "Не указано"))
            url = vacancy_data.get("url", "#")
            description = vacancy_data.get("text", "")

            if status == "APPROVED":
                # Сохраняем одобренную вакансию и автогенерированное сопроводительное письмо
                storage_manager.save_approved_vacancy(
                    company=company,
                    title=title,
                    url=url,
                    cover_letter=result_text,
                    description=description
                )
                self.update_status(f"✓ ОДОБРЕНО: {title} в {company}!", COLOR_CYAN_NEON)
            elif status == "REJECTED":
                # Сохраняем причину отказа в журнал отклоненных
                storage_manager.save_rejected_vacancy(
                    company=company,
                    title=title,
                    url=url,
                    reason=result_text
                )
                # Выводим компактный лаконичный статус на главный экран
                self.update_status(f"✕ Отклонено ИИ: {title} в {company} (причина в результатах)", COLOR_RED)
            else:
                self.update_status(f"⚠ Сбой ИИ: {result_text}", COLOR_RED)
        except Exception as e:
            self.update_status(f"⚠ Сбой обработки: {str(e)}", COLOR_RED)

    def open_results(self):
        """Открывает окно со списком одобренных ИИ вакансий"""
        results_ui.open_window(self)

if __name__ == "__main__":
    app = JobHunterApp()
    app.mainloop()