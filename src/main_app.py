# main_app.py
import os
import sys
import json
import threading
import queue
import time
import webbrowser
import customtkinter as ctk
from tkinter import messagebox, filedialog
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image, ImageTk
import jh_ai_engine
import jh_storage_manager
import jh_results_ui
import jh_version
import jh_i18n
from jh_i18n import tr

# =====================================================================
# НАСТРОЙКА DPI И СИСТЕМНОГО ОКРУЖЕНИЯ Windows
# =====================================================================
try:
    import ctypes
    # Включаем DPI-Awareness, чтобы шрифты на экранах (2K/4K) были идеально четкими
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
jh_storage_manager.init_db()

# Цветовая неоновая космическая палитра
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

# Доступные модели по провайдерам
ALL_PROVIDERS_MODELS = {
    "Gemini": ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.0-pro"],
    "OpenAI": ["gpt-5-mini", "gpt-5", "o3-mini"],
    "Anthropic": ["claude-4-haiku", "claude-4-sonnet", "claude-4-opus"],
    "DeepSeek": ["deepseek-chat", "deepseek-reasoner"],
    "Ollama": ["local-model"],
    "LM Studio": ["local-model"]
}

# Провайдеры, работающие через локальный сервер (без облачного API-ключа).
LOCAL_PROVIDERS = ("Ollama", "LM Studio")
# Список всех провайдеров для выпадающего меню (порядок сохраняется).
PROVIDER_ORDER = ["Gemini", "OpenAI", "Anthropic", "DeepSeek", "Ollama", "LM Studio"]

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


def _apply_icon_win32(window):
    """Set window icon via both Tkinter and Win32 API — belt-and-suspenders for CTkToplevel."""
    if not os.path.exists(ICON_PATH):
        return
    try:
        window.iconbitmap(ICON_PATH)
    except Exception:
        pass
    try:
        import ctypes
        # GA_ROOT(2) надёжно находит корневое окно даже для вложенных CTkToplevel
        GA_ROOT = 2
        hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), GA_ROOT)
        if not hwnd:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        LR_LOADFROMFILE, LR_DEFAULTSIZE, IMAGE_ICON, WM_SETICON = 0x0010, 0x0040, 1, 0x0080
        icon_big = ctypes.windll.user32.LoadImageW(
            None, ICON_PATH, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        icon_small = ctypes.windll.user32.LoadImageW(
            None, ICON_PATH, IMAGE_ICON, 16, 16, LR_LOADFROMFILE
        )
        if icon_big:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, icon_big)
        if icon_small:
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, icon_small)
    except Exception:
        pass

def center_window(window, width, height, parent=None):
    """
    Центрирует окно без мерцания (alpha=0 → geometry → alpha=1).

    Координатная модель CustomTkinter + DPI-aware Windows:
      • winfo_rootx / winfo_width / winfo_screenwidth — физические пиксели.
      • geometry("WxH+X+Y"): CTk умножает W и H на sc внутри себя,
        но X и Y передаёт ОС как есть — они должны быть физическими пикселями.
      Формула: переводим логические w/h в физические (× sc), считаем X/Y
      в физических пикселях, передаём в geometry().
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
            try:
                sc = window._get_window_scaling()
            except Exception:
                sc = 1.0

            # Логические размеры окна → физические пиксели для арифметики центрирования
            child_phys_w = width * sc
            child_phys_h = height * sc

            if parent and parent.winfo_exists():
                # winfo_* возвращают физические пиксели
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                x = int(px + (pw - child_phys_w) / 2)
                y = int(py + (ph - child_phys_h) / 2)
            else:
                sw = window.winfo_screenwidth()
                sh = window.winfo_screenheight()
                x = int((sw - child_phys_w) / 2)
                y = int((sh - child_phys_h) / 2)

            # width/height — логические (CTk умножит на sc); x/y — физические (CTk не трогает)
            window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        except Exception as e:
            print(f"[Резервное центрирование]: {e}")
            window.geometry(f"{width}x{height}")
        finally:
            try:
                window.attributes("-alpha", 1.0)
                window.deiconify()
            except Exception:
                pass

    window.after(15, _apply_centered_position)

def bind_russian_hotkeys(widget):
    """Обработка горячих клавиш Ctrl+C, Ctrl+V, Ctrl+A, Ctrl+X для русской раскладки."""
    target = widget
    if hasattr(widget, "_entry"):
        target = widget._entry
    elif hasattr(widget, "_textbox"):
        target = widget._textbox

    def handle_control_keys(event):
        key = event.keysym.lower()
        keycode = event.keycode
        
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
# FLASK СЕРВЕР (ПРИЕМ ДАННЫХ ИЗ РАСШИРЕНИЯ)
# =====================================================================
flask_app = Flask(__name__)
CORS(flask_app)
app_instance = None

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    global app_instance
    if not app_instance or not app_instance.is_active:
        return jsonify({"status": "ignored", "reason": "Assistant is offline"}), 200
        
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "reason": "No data received"}), 400
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
        self._paused_mode = False    # True when stopped with items still in queue
        self._btn_resume = None
        self._btn_reset = None
        self._worker_has_item = False  # True while worker holds a dequeued item
        self._batch_id = 0             # incremented on each new enqueue; debounces done-notification
        self._local_server_ok = False   # Tracks local server reachability; True for cloud providers
        self._server_poll_after_id = None  # after() handle for the server poll loop
        # Session counters (reset on each START)
        self._session_processed = 0
        self._session_approved = 0
        self._session_rejected = 0
        # Дескрипторы werkzeug-сервера для корректного graceful-shutdown
        # и предотвращения утечки/дублирования потоков Flask.
        self.flask_server = None      # werkzeug.serving.BaseWSGIServer
        self.flask_thread = None      # поток, в котором крутится serve_forever
        # Set by run_flask_server() after make_server() binds the socket.
        # _activate_when_ready() polls this — no blocking I/O on the main thread.
        self._flask_ready = threading.Event()

        # Потокобезопасная очередь для вакансий
        self.vacancy_queue = queue.Queue()
        self.worker_thread = None
        self.stop_worker_event = threading.Event()
        
        # Загружаем конфигурацию и применяем язык интерфейса
        self.app_config = jh_storage_manager.load_config()
        jh_i18n.set_language(self.app_config.get("language", "en"))

        self.title(jh_version.get_window_title() + " Global")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_DARK)
        ctk.set_appearance_mode("dark")
        
        center_window(self, 680, 770)
        force_dark_title_bar(self)
        
        # Протокол чистого закрытия приложения (высвобождает сокеты Flask)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        try:
            if os.path.exists(ICON_PATH):
                self.iconbitmap(ICON_PATH)
        except Exception:
            pass

        self.setup_ui()
        self.load_config_to_ui()

    def on_closing(self):
        """Безопасное и чистое закрытие приложения для предотвращения зомби-процессов и блокировок портов."""
        self.is_active = False
        self.stop_worker_event.set()
        if self._server_poll_after_id is not None:
            try:
                self.after_cancel(self._server_poll_after_id)
            except Exception:
                pass

        # Корректно гасим werkzeug-сервер: разблокируем serve_forever, закрываем
        # слушающий сокет и дожидаемся завершения потока. Это устраняет утечку
        # потока/сокета Flask при закрытии главного окна.
        try:
            self.shutdown_flask_server()
        except Exception as e:
            print(f"[Закрытие]: Ошибка остановки Flask: {e}")

        # Даём worker-потоку шанс выйти из текущей итерации.
        worker = getattr(self, "worker_thread", None)
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)

        try:
            time.sleep(0.1)
        except Exception:
            pass
        os._exit(0)

    def load_and_resize_logo(self, height_pixels):
        """Загружает логотип и масштабирует его под DPI экрана."""
        try:
            try:
                scaling = self._get_window_scaling()
            except Exception:
                scaling = 1.0

            target_height = int(height_pixels * scaling)
            
            logo_img = None
            if os.path.exists(LOGO_PNG_PATH):
                logo_img = Image.open(LOGO_PNG_PATH)
            elif os.path.exists(ICON_PATH):
                logo_img = Image.open(ICON_PATH)

            if logo_img:
                aspect_ratio = logo_img.width / logo_img.height
                target_width = int(target_height * aspect_ratio)
                logo_img = logo_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                return ctk.CTkImage(
                    light_image=logo_img,
                    dark_image=logo_img,
                    size=(int(target_width / scaling), int(target_height / scaling))
                )
        except Exception as e:
            print(f"[Ошибка загрузки логотипа]: {e}")
        return None

    def setup_ui(self):
        """Создает элементы управления в главном окне."""
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
        
        self._subtitle_lbl = ctk.CTkLabel(
            self,
            text=tr("subtitle"),
            font=("Arial", 12),
            text_color=COLOR_TEXT_MUTED
        )
        self._subtitle_lbl.pack(pady=(0, 20))

        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.pack(pady=10, padx=30, fill="x")
        
        self.first_name_input = ctk.CTkEntry(
            name_frame,
            placeholder_text=tr("first_name_ph"),
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
            placeholder_text=tr("last_name_ph"),
            height=45,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text_color=COLOR_TEXT_MUTED
        )
        self.last_name_input.pack(side="right", fill="x", expand=True, padx=(10, 0))
        bind_russian_hotkeys(self.last_name_input)

        resume_header_frame = ctk.CTkFrame(self, fg_color="transparent")
        resume_header_frame.pack(anchor="w", padx=30, pady=(15, 5), fill="x")
        
        self._resume_lbl = ctk.CTkLabel(
            resume_header_frame,
            text=tr("resume_label"),
            font=("Arial", 13, "bold"),
            text_color=COLOR_TEXT_LIGHT
        )
        self._resume_lbl.pack(side="left")
        
        def paste_to_resume():
            try:
                clipboard_text = self.clipboard_get()
                self.resume_input.delete("0.0", "end")
                self.resume_input.insert("0.0", clipboard_text.strip())
            except Exception:
                pass

        # Icon-only compact buttons, packed right-to-left:
        # ⚙ (rightmost) → 📋 → 📂 (furthest from right edge)
        self.btn_ai_settings = ctk.CTkButton(
            resume_header_frame,
            text="⚙",
            width=30,
            height=30,
            font=("Arial", 14),
            fg_color=COLOR_CARD_BG,
            hover_color=COLOR_INPUT_BG,
            text_color=COLOR_CYAN_NEON,
            border_width=1,
            border_color=COLOR_CYAN_NEON,
            command=self.open_ai_settings_window
        )
        self.btn_ai_settings.pack(side="right")

        self.btn_history = ctk.CTkButton(
            resume_header_frame,
            text="📂",
            width=30,
            height=30,
            font=("Arial", 14),
            fg_color=COLOR_CARD_BG,
            hover_color=COLOR_INPUT_BG,
            text_color=COLOR_GOLD,
            border_width=1,
            border_color=COLOR_GOLD,
            command=self.open_resume_history
        )
        self.btn_history.pack(side="right", padx=(0, 4))

        self.btn_paste_resume = ctk.CTkButton(
            resume_header_frame,
            text="📋",
            width=30,
            height=30,
            font=("Arial", 14),
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK,
            command=paste_to_resume
        )
        self.btn_paste_resume.pack(side="right", padx=(0, 4))

        self.btn_pdf_import = ctk.CTkButton(
            resume_header_frame,
            text=tr("btn_pdf_import"),
            width=38,
            height=30,
            font=("Arial", 11, "bold"),
            fg_color=COLOR_CARD_BG,
            hover_color=COLOR_INPUT_BG,
            text_color=COLOR_RED,
            border_width=1,
            border_color=COLOR_RED,
            command=self.import_resume_from_pdf
        )
        self.btn_pdf_import.pack(side="right", padx=(0, 4))
        
        self.resume_input = ctk.CTkTextbox(
            self, 
            height=180, 
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            border_width=1,
            text_color=COLOR_TEXT_LIGHT
        )
        self.resume_input.pack(pady=5, padx=30, fill="x")
        bind_russian_hotkeys(self.resume_input)

        self._filter_lbl = ctk.CTkLabel(
            self,
            text=tr("filter_label"),
            font=("Arial", 13, "bold"),
            text_color=COLOR_TEXT_LIGHT
        )
        self._filter_lbl.pack(anchor="w", padx=30, pady=(15, 5))
        
        # Контейнер для фильтров
        filter_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=8)
        filter_frame.pack(pady=5, padx=30, fill="x")
        
        # КОРРЕКТНЫЕ И СТАБИЛЬНЫЕ НАСТРОЙКИ ЧЕКБОКСОВ (Размер 20х20 исключает оверлап текстуры)
        self.cb_remote = ctk.CTkCheckBox(
            filter_frame,
            text=tr("cb_remote"),
            text_color=COLOR_TEXT_LIGHT,
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_TEXT_MUTED,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        )
        self.cb_remote.pack(side="left", padx=15, pady=12)
        self.cb_remote.select()

        self.cb_office = ctk.CTkCheckBox(
            filter_frame,
            text=tr("cb_office"),
            text_color=COLOR_TEXT_LIGHT,
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_TEXT_MUTED,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        )
        self.cb_office.pack(side="left", padx=15, pady=12)

        self.cb_hybrid = ctk.CTkCheckBox(
            filter_frame,
            text=tr("cb_hybrid"),
            text_color=COLOR_TEXT_LIGHT,
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_TEXT_MUTED,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        )
        self.cb_hybrid.pack(side="left", padx=15, pady=12)

        # Location filter: checkbox + country entry
        loc_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        loc_frame.pack(side="right", padx=(0, 10), pady=8)

        self.cb_location = ctk.CTkCheckBox(
            loc_frame,
            text=tr("cb_location"),
            text_color=COLOR_TEXT_LIGHT,
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_TEXT_MUTED,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        )
        self.cb_location.pack(side="left")
        self.cb_location.select()

        self.location_entry = ctk.CTkEntry(
            loc_frame,
            placeholder_text=tr("location_placeholder"),
            width=130,
            height=30,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text_color=COLOR_TEXT_MUTED,
            font=("Arial", 11)
        )
        self.location_entry.pack(side="left", padx=(8, 0))

        # Важнейший фикс: сброс фокуса при клике на чекбоксы для предотвращения залипания подсветки
        def reset_widget_focus(event):
            self.focus()

        self.cb_remote.bind("<ButtonRelease-1>", reset_widget_focus)
        self.cb_office.bind("<ButtonRelease-1>", reset_widget_focus)
        self.cb_hybrid.bind("<ButtonRelease-1>", reset_widget_focus)
        self.cb_location.bind("<ButtonRelease-1>", reset_widget_focus)

        self.status_lbl = ctk.CTkLabel(
            self,
            text=tr("status_loaded"),
            font=("Arial", 12, "bold"),
            text_color=COLOR_CYAN_NEON,
            wraplength=600
        )
        self.status_lbl.pack(pady=10)

        self._toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._toggle_frame.pack(pady=5, padx=30, fill="x")
        self._show_normal_toggle()
        
        self._btn_results = ctk.CTkButton(
            self,
            text=tr("btn_results"),
            font=("Arial", 13, "bold"),
            fg_color=COLOR_GOLD,
            hover_color=COLOR_GOLD_HOVER,
            text_color=COLOR_BG_DARK,
            height=45,
            command=self.open_results
        )
        self._btn_results.pack(pady=(5, 20), padx=30, fill="x")

    def retranslate_main_ui(self):
        """Обновляет все локализуемые строки главного окна при смене языка."""
        try:
            self._subtitle_lbl.configure(text=tr("subtitle"))
            self._resume_lbl.configure(text=tr("resume_label"))
            self._filter_lbl.configure(text=tr("filter_label"))
            self.cb_remote.configure(text=tr("cb_remote"))
            self.cb_office.configure(text=tr("cb_office"))
            self.cb_hybrid.configure(text=tr("cb_hybrid"))
            self.cb_location.configure(text=tr("cb_location"))
            self.location_entry.configure(placeholder_text=tr("location_placeholder"))
            self._btn_results.configure(text=tr("btn_results"))
            # Toggle area: three states — running / paused-with-queue / stopped
            if self.is_active:
                try:
                    self.btn_toggle.configure(text=tr("btn_stop"))
                except Exception:
                    pass
            elif self._paused_mode:
                try:
                    self._btn_resume.configure(text=tr("btn_resume"))
                    self._btn_reset.configure(text=tr("btn_reset_queue"))
                except Exception:
                    pass
            else:
                try:
                    self.btn_toggle.configure(text=tr("btn_start"))
                except Exception:
                    pass
            # Placeholders для полей ввода
            self.first_name_input.configure(placeholder_text=tr("first_name_ph"))
            self.last_name_input.configure(placeholder_text=tr("last_name_ph"))
        except Exception as e:
            print(f"[i18n]: retranslate_main_ui error: {e}")

    def _show_normal_toggle(self):
        """Renders a single START button inside the toggle frame."""
        for w in self._toggle_frame.winfo_children():
            w.destroy()
        self.btn_toggle = ctk.CTkButton(
            self._toggle_frame,
            text=tr("btn_start"),
            font=("Arial", 15, "bold"),
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK,
            height=50,
            command=self.toggle_assistant
        )
        self.btn_toggle.pack(fill="x")

    def _show_paused_toggle(self, q_size=0):
        """Renders Resume (80%) + Reset Queue (20%) buttons inside the toggle frame."""
        self._paused_mode = True
        for w in self._toggle_frame.winfo_children():
            w.destroy()
        self._toggle_frame.columnconfigure(0, weight=4)
        self._toggle_frame.columnconfigure(1, weight=1)
        self._btn_resume = ctk.CTkButton(
            self._toggle_frame,
            text=tr("btn_resume"),
            font=("Arial", 15, "bold"),
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK,
            height=50,
            command=self.toggle_assistant
        )
        self._btn_resume.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._btn_reset = ctk.CTkButton(
            self._toggle_frame,
            text=tr("btn_reset_queue"),
            font=("Arial", 13, "bold"),
            fg_color=COLOR_RED,
            hover_color=COLOR_RED_HOVER,
            text_color=COLOR_TEXT_LIGHT,
            height=50,
            command=self._reset_queue
        )
        self._btn_reset.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _reset_queue(self):
        """Drains the paused queue and returns to the normal START button."""
        while not self.vacancy_queue.empty():
            try:
                self.vacancy_queue.get_nowait()
            except queue.Empty:
                break
        self._paused_mode = False
        self._show_normal_toggle()
        self.status_lbl.configure(text=tr("status_stopped"), text_color=COLOR_RED)

    def show_api_help(self):
        """Отображает справку о получении бесплатного API-ключа."""
        help_win = ctk.CTkToplevel(self)
        help_win.withdraw()
        help_win.title(tr("help_win_title"))
        help_win.configure(fg_color=COLOR_BG_DARK)

        force_dark_title_bar(help_win)

        help_header = ctk.CTkFrame(help_win, fg_color="transparent")
        help_header.pack(pady=(20, 10))
        help_logo = self.load_and_resize_logo(22)
        if help_logo:
            ctk.CTkLabel(help_header, image=help_logo, text="").pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            help_header,
            text=tr("help_title"),
            font=("Arial", 14, "bold"),
            text_color=COLOR_CYAN_NEON
        ).pack(side="left")

        ctk.CTkLabel(
            help_win,
            text=tr("help_text"),
            font=("Arial", 11),
            text_color=COLOR_TEXT_LIGHT,
            justify="left"
        ).pack(padx=25, pady=5)

        ctk.CTkButton(
            help_win,
            text=tr("help_btn"),
            font=("Arial", 11, "bold"),
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK,
            height=36,
            command=lambda: webbrowser.open("https://aistudio.google.com/")
        ).pack(pady=(15, 5))

        def _show_help():
            if not help_win.winfo_exists(): return
            try: help_win.attributes("-alpha", 0.0)
            except Exception: pass
            try:
                help_win.update_idletasks()
                w, h = 460, 260
                try:
                    sc = help_win._get_window_scaling()
                except Exception:
                    sc = 1.0
                # w/h логические → физические для арифметики; x/y остаются физическими
                child_phys_w, child_phys_h = w * sc, h * sc
                px = self.winfo_rootx()
                py = self.winfo_rooty()
                pw = self.winfo_width()
                ph = self.winfo_height()
                x = int(px + (pw - child_phys_w) / 2)
                y = int(py + (ph - child_phys_h) / 2)
                help_win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
            except Exception:
                help_win.geometry("460x260")
            help_win.deiconify()
            help_win.grab_set()
            help_win.focus_force()
            def _fin():
                if not help_win.winfo_exists(): return
                try:
                    _apply_icon_win32(help_win)
                except Exception: pass
                try: help_win.attributes("-alpha", 1.0)
                except Exception: pass
                help_win.after(350, lambda: _apply_icon_win32(help_win) if help_win.winfo_exists() else None)
            help_win.after(100, _fin)
        help_win.after(120, _show_help)

    def set_cloud_provider_status(self, provider):
        """Стандартная статус-плашка для облачных провайдеров."""
        api_key = self.app_config.get("api_keys", {}).get(provider, "").strip()
        if not api_key:
            self.update_status(tr("status_key_required", provider=provider), COLOR_GOLD)
        else:
            self.update_status(tr("status_loaded"), COLOR_CYAN_NEON)

    def update_local_server_status(self, provider, _silent=False):
        """
        Runs a background check of the local server and updates the status label.
        When _silent=True (called from the poll loop), skips the 'checking...' flash.
        Automatically reschedules itself every 10s while local provider is active.
        """
        servers = self.app_config.get("local_servers", {}) or {}
        defaults = {"Ollama": "http://localhost:11434", "LM Studio": "http://localhost:1234"}
        base_url = servers.get(provider, defaults.get(provider))

        if not _silent:
            self.update_status(tr("status_local_check", provider=provider), COLOR_GOLD)

        def _probe():
            try:
                is_up, msg = jh_ai_engine.check_local_server(provider, base_url)
            except Exception as e:
                print(f"[Локальный статус]: Ошибка проверки сервера: {e}")
                is_up, msg = False, "Server unreachable"

            def _apply():
                if not self.winfo_exists():
                    return
                prev_ok = self._local_server_ok
                self._local_server_ok = is_up
                color = COLOR_CYAN_NEON if is_up else COLOR_GOLD
                prefix = "● " if is_up else "⚠ "
                if not self.is_active:
                    self.update_status(prefix + msg, color)
                elif not is_up and prev_ok:
                    # Server went offline while assistant was running
                    self.update_status(tr("status_server_down", provider=provider), COLOR_RED)

                # Reschedule if still on this local provider
                if self.app_config.get("current_provider") == provider and provider in LOCAL_PROVIDERS:
                    if self._server_poll_after_id is not None:
                        try:
                            self.after_cancel(self._server_poll_after_id)
                        except Exception:
                            pass
                    self._server_poll_after_id = self.after(
                        10000, lambda: self.update_local_server_status(provider, _silent=True)
                    )

            try:
                self.after(0, _apply)
            except Exception:
                pass

        threading.Thread(target=_probe, daemon=True).start()

    def maybe_show_local_llm_warning(self, parent_win):
        """
        Показывает модальное предупреждение о требованиях к скорости локальных LLM,
        если флаг show_local_llm_warning в config.json включён (или отсутствует).
        Содержит чекбокс 'Больше не показывать', сохраняющий флаг в config.json.
        """
        if not jh_storage_manager.should_show_local_warning(self.app_config):
            return

        warn = ctk.CTkToplevel(parent_win)
        warn.withdraw()
        warn.title(tr("warn_win_title"))
        warn.configure(fg_color=COLOR_BG_DARK)
        force_dark_title_bar(warn)
        warn.transient(parent_win)

        ctk.CTkLabel(
            warn,
            text=tr("warn_title"),
            font=("Arial", 16, "bold"),
            text_color=COLOR_GOLD
        ).pack(pady=(20, 10), padx=20)

        ctk.CTkLabel(
            warn,
            text=tr("warn_text", min_tps=jh_ai_engine.MIN_TOKENS_PER_SEC),
            font=("Arial", 11),
            text_color=COLOR_TEXT_LIGHT,
            justify="left"
        ).pack(padx=25, pady=5)

        dont_show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            warn,
            text=tr("warn_dont_show"),
            variable=dont_show_var,
            text_color=COLOR_TEXT_MUTED,
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_TEXT_MUTED,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        ).pack(pady=(10, 5))

        def close_warning():
            if dont_show_var.get():
                self.app_config["show_local_llm_warning"] = False
                # Асинхронное сохранение: read-modify-write на диск не блокирует UI-поток
                self._set_show_local_warning_async(False)
            try:
                warn.grab_release()
            except Exception:
                pass
            warn.destroy()
            try:
                parent_win.focus_force()
            except Exception:
                pass

        ctk.CTkButton(
            warn,
            text=tr("warn_ok"),
            font=("Arial", 12, "bold"),
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK,
            height=38,
            command=close_warning
        ).pack(pady=(10, 15))

        warn.protocol("WM_DELETE_WINDOW", close_warning)

        def _show_warn():
            if not warn.winfo_exists(): return
            try: warn.attributes("-alpha", 0.0)
            except Exception: pass
            try:
                warn.update_idletasks()
                w, h = 500, 400
                try:
                    sc = warn._get_window_scaling()
                except Exception:
                    sc = 1.0
                # w/h логические → физические для арифметики; x/y остаются физическими
                child_phys_w, child_phys_h = w * sc, h * sc
                if parent_win and parent_win.winfo_exists():
                    px = parent_win.winfo_rootx()
                    py = parent_win.winfo_rooty()
                    pw = parent_win.winfo_width()
                    ph = parent_win.winfo_height()
                    x = int(px + (pw - child_phys_w) / 2)
                    y = int(py + (ph - child_phys_h) / 2)
                else:
                    x = int((warn.winfo_screenwidth() - child_phys_w) / 2)
                    y = int((warn.winfo_screenheight() - child_phys_h) / 2)
                warn.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
            except Exception:
                warn.geometry("500x400")
            warn.deiconify()
            warn.grab_set()
            warn.focus_force()
            def _fin():
                if not warn.winfo_exists(): return
                try:
                    _apply_icon_win32(warn)
                except Exception: pass
                try: warn.attributes("-alpha", 1.0)
                except Exception: pass
                warn.after(350, lambda: _apply_icon_win32(warn) if warn.winfo_exists() else None)
            warn.after(100, _fin)
        warn.after(120, _show_warn)

    def open_ai_settings_window(self):
        """Модальное окно настройки провайдера ИИ с блокировкой слайдера для локальных."""
        settings_win = ctk.CTkToplevel(self)
        settings_win.withdraw()
        settings_win.title("AI Settings")
        settings_win.configure(fg_color=COLOR_BG_DARK)
        force_dark_title_bar(settings_win)

        # ── Заголовочный фрейм: title | help | EN/RU ──────────────────────────
        title_frame = ctk.CTkFrame(settings_win, fg_color="transparent")
        title_frame.pack(pady=(18, 8), padx=30, fill="x")
        title_frame.columnconfigure(0, weight=1)
        title_frame.columnconfigure(1, weight=0)
        title_frame.columnconfigure(2, weight=0)

        ctk.CTkLabel(
            title_frame,
            text=tr("settings_title"),
            font=("Arial", 16, "bold"),
            text_color=COLOR_CYAN_NEON
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            title_frame,
            text=tr("settings_help"),
            font=("Arial", 11, "bold"),
            text_color=COLOR_CYAN_NEON,
            fg_color="transparent",
            hover_color=COLOR_INPUT_BG,
            width=75,
            height=25,
            command=self.show_api_help
        ).grid(row=0, column=1, sticky="e", padx=(0, 6))

        # EN / RU переключатель ────────────────────────────────────────────────
        lang_seg = ctk.CTkSegmentedButton(
            title_frame,
            values=["EN", "RU"],
            font=("Arial", 11, "bold"),
            selected_color=COLOR_CYAN_NEON,
            selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG,
            unselected_hover_color=COLOR_INPUT_BG,
            text_color=COLOR_BG_DARK,
            width=70,
            height=25,
        )
        lang_seg.set(jh_i18n.get_language().upper())
        lang_seg.grid(row=0, column=2, sticky="e")

        # ── Разделитель ────────────────────────────────────────────────────────
        ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", padx=30, pady=(0, 12))

        # ── Провайдер ──────────────────────────────────────────────────────────
        ctk.CTkLabel(
            settings_win,
            text=tr("provider_label"),
            font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", padx=30, pady=(0, 3))

        model_checkboxes = []
        model_group_frame = ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, corner_radius=8)

        temp_api_keys = self.app_config.get("api_keys", {}).copy()
        current_prov_var = ctk.StringVar(value=self.app_config.get("current_provider", "Gemini"))

        # ── Ссылка на слайдер (создаётся позже, guard через список) ───────────
        _slider_ref = [None]
        _delay_lbl_var = ctk.StringVar()

        def _update_delay_label(val):
            _delay_lbl_var.set(tr("delay_label", val=int(float(val))))

        def _apply_slider_state(provider):
            slider = _slider_ref[0]
            if slider is None:
                return
            slider.configure(state="normal")
            _update_delay_label(slider.get())

        def _reapply_show_mask():
            """CTkEntry сбрасывает show='*' при configure(state=...) — восстанавливаем."""
            try:
                api_key_entry.configure(show="*")
            except Exception:
                try:
                    api_key_entry._entry.configure(show="*")
                except Exception:
                    pass

        def apply_local_key_field_state(provider):
            is_local = provider in LOCAL_PROVIDERS
            if is_local:
                temp_api_keys[provider] = "local"
                try:
                    api_key_entry.configure(state="normal")
                    api_key_entry.delete(0, "end")
                    api_key_entry.configure(
                        state="disabled",
                        placeholder_text=tr("key_placeholder_local")
                    )
                    _reapply_show_mask()
                except Exception as e:
                    print(f"[Настройки ИИ]: Не удалось заблокировать поле ключа: {e}")
            else:
                try:
                    api_key_entry.configure(
                        state="normal",
                        placeholder_text=tr("key_placeholder")
                    )
                    saved_key = temp_api_keys.get(provider, "")
                    api_key_entry.delete(0, "end")
                    if saved_key:
                        api_key_entry.insert(0, saved_key)
                    # Re-apply AFTER insert: configure(state=...) and insert()
                    # both reset show="*" in CTkEntry internally.
                    _reapply_show_mask()
                except Exception as e:
                    print(f"[Настройки ИИ]: Не удалось разблокировать поле ключа: {e}")

        # Флаг: при первом (инициализационном) вызове on_provider_changed поле
        # api_key_entry только что создано и пустое — захватывать нечего.
        # Без флага пустой get() перетирает сохранённый ключ в temp_api_keys.
        _initialized = [False]

        def on_provider_changed(new_provider):
            if _initialized[0]:
                old_provider = self.app_config.get("current_provider", "Gemini")
                if old_provider not in LOCAL_PROVIDERS:
                    try:
                        if str(api_key_entry.cget("state")) != "disabled":
                            temp_api_keys[old_provider] = api_key_entry.get().strip()
                    except Exception:
                        pass

            self.app_config["current_provider"] = new_provider
            apply_local_key_field_state(new_provider)
            _apply_slider_state(new_provider)

            for cb in model_checkboxes:
                cb.destroy()
            model_checkboxes.clear()

            for m_name in ALL_PROVIDERS_MODELS.get(new_provider, []):
                active_list = self.app_config["active_models"].get(new_provider, [])
                cb_var = ctk.BooleanVar(value=(m_name in active_list))
                cb = ctk.CTkCheckBox(
                    model_group_frame,
                    text=m_name,
                    variable=cb_var,
                    text_color=COLOR_TEXT_LIGHT,
                    fg_color=COLOR_CYAN_NEON,
                    hover_color=COLOR_CYAN_HOVER,
                    border_color=COLOR_TEXT_MUTED,
                    checkbox_width=20,
                    checkbox_height=20,
                    border_width=2,
                    checkmark_color=COLOR_TEXT_LIGHT,
                    command=lambda name=m_name, var=cb_var: update_active_models(new_provider, name, var.get())
                )
                cb.pack(anchor="w", padx=15, pady=6)
                model_checkboxes.append(cb)

            if new_provider in LOCAL_PROVIDERS:
                self._local_server_ok = False
                self.maybe_show_local_llm_warning(settings_win)
                self.update_local_server_status(new_provider)
            else:
                self._local_server_ok = True
                self.set_cloud_provider_status(new_provider)

        def update_active_models(provider, name, is_selected):
            if provider not in self.app_config["active_models"]:
                self.app_config["active_models"][provider] = []
            curr = self.app_config["active_models"][provider]
            if is_selected and name not in curr:
                curr.append(name)
            elif not is_selected and name in curr:
                curr.remove(name)

        provider_dropdown = ctk.CTkOptionMenu(
            settings_win,
            values=PROVIDER_ORDER,
            variable=current_prov_var,
            command=on_provider_changed,
            fg_color=COLOR_CARD_BG,
            button_color=COLOR_INPUT_BG,
            button_hover_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            dropdown_fg_color=COLOR_CARD_BG,
            dropdown_hover_color=COLOR_INPUT_BG,
            dropdown_text_color=COLOR_TEXT_LIGHT
        )
        provider_dropdown.pack(pady=(3, 12), padx=30, fill="x")

        ctk.CTkLabel(
            settings_win,
            text=tr("key_label"),
            font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", padx=30, pady=(0, 3))

        api_key_entry = ctk.CTkEntry(
            settings_win,
            height=40,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text=tr("key_placeholder"),
            show="*"
        )
        api_key_entry.pack(pady=(3, 12), padx=30, fill="x")
        bind_russian_hotkeys(api_key_entry)

        ctk.CTkLabel(
            settings_win,
            text=tr("models_label"),
            font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", padx=30, pady=(0, 3))

        model_group_frame.pack(pady=(3, 14), padx=30, fill="x")

        # Инициализируем состояние под текущего провайдера.
        # После вызова взводим флаг — теперь on_provider_changed будет захватывать ключ.
        on_provider_changed(current_prov_var.get())
        _initialized[0] = True

        # ── Разделитель ────────────────────────────────────────────────────────
        ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", padx=30, pady=(0, 12))

        # ── Слайдер задержки ───────────────────────────────────────────────────
        ctk.CTkLabel(
            settings_win,
            textvariable=_delay_lbl_var,
            font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", padx=30, pady=(0, 3))

        current_delay = self.app_config.get("request_delay", 15)
        delay_slider = ctk.CTkSlider(
            settings_win,
            from_=0,
            to=60,
            number_of_steps=60,
            command=_update_delay_label,
            button_color=COLOR_CYAN_NEON,
            button_hover_color=COLOR_CYAN_HOVER,
            progress_color=COLOR_CYAN_NEON,
            fg_color=COLOR_INPUT_BG
        )
        delay_slider.pack(pady=(3, 14), padx=30, fill="x")
        delay_slider.set(current_delay)
        _slider_ref[0] = delay_slider
        _apply_slider_state(current_prov_var.get())

        # ── Разделитель ────────────────────────────────────────────────────────
        ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", padx=30, pady=(0, 12))

        # ── Строгость фильтра ──────────────────────────────────────────────────
        ctk.CTkLabel(
            settings_win,
            text=tr("strictness_label"),
            font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", padx=30, pady=(0, 3))

        strictness_labels = [tr("strictness_mild"), tr("strictness_balanced"), tr("strictness_strict")]
        strictness_seg = ctk.CTkSegmentedButton(
            settings_win,
            values=strictness_labels,
            font=("Arial", 11, "bold"),
            selected_color=COLOR_CYAN_NEON,
            selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG,
            unselected_hover_color=COLOR_INPUT_BG,
            text_color=COLOR_BG_DARK,
        )
        strictness_seg.pack(pady=(3, 14), padx=30, fill="x")
        current_strictness = self.app_config.get("filter_strictness", 2)
        strictness_seg.set(strictness_labels[max(0, min(2, current_strictness - 1))])

        # ── Длина сопроводительного письма ─────────────────────────────────────
        ctk.CTkLabel(
            settings_win,
            text=tr("letter_length_label"),
            font=("Arial", 12, "bold"),
            text_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", padx=30, pady=(0, 3))

        letter_labels = [tr("letter_short"), tr("letter_balanced"), tr("letter_detailed")]
        letter_seg = ctk.CTkSegmentedButton(
            settings_win,
            values=letter_labels,
            font=("Arial", 11, "bold"),
            selected_color=COLOR_CYAN_NEON,
            selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG,
            unselected_hover_color=COLOR_INPUT_BG,
            text_color=COLOR_BG_DARK,
        )
        letter_seg.pack(pady=(3, 14), padx=30, fill="x")
        current_letter = self.app_config.get("letter_length", 2)
        letter_seg.set(letter_labels[max(0, min(2, current_letter - 1))])

        # ── Разделитель ────────────────────────────────────────────────────────
        ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", padx=30, pady=(0, 12))

        # ── Уведомления ────────────────────────────────────────────────────────
        notif_var = ctk.BooleanVar(value=bool(self.app_config.get("notifications_enabled", True)))
        notif_cb = ctk.CTkCheckBox(
            settings_win,
            text=tr("cb_notifications"),
            variable=notif_var,
            text_color=COLOR_TEXT_LIGHT,
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            border_color=COLOR_TEXT_MUTED,
            checkbox_width=20,
            checkbox_height=20,
            border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        )
        notif_cb.pack(anchor="w", padx=30, pady=(0, 14))

        # ── Сохранение / закрытие ──────────────────────────────────────────────
        def _collect_state():
            """Собирает текущее состояние формы в self.app_config без закрытия окна."""
            active_prov = current_prov_var.get()
            if active_prov in LOCAL_PROVIDERS:
                temp_api_keys[active_prov] = "local"
            else:
                try:
                    if str(api_key_entry.cget("state")) != "disabled":
                        temp_api_keys[active_prov] = api_key_entry.get().strip()
                except Exception:
                    pass
            self.app_config["current_provider"] = active_prov
            self.app_config["api_keys"] = temp_api_keys
            self.app_config["request_delay"] = int(delay_slider.get())
            # Strictness: map label index → 1/2/3
            try:
                s_idx = strictness_labels.index(strictness_seg.get())
            except ValueError:
                s_idx = 1
            self.app_config["filter_strictness"] = s_idx + 1
            # Letter length: map label index → 1/2/3
            try:
                l_idx = letter_labels.index(letter_seg.get())
            except ValueError:
                l_idx = 1
            self.app_config["letter_length"] = l_idx + 1
            self.app_config["notifications_enabled"] = bool(notif_var.get())

        def save_and_close():
            _collect_state()
            jh_storage_manager.save_config(self.app_config)
            self.update_status(tr("status_saved"), COLOR_CYAN_NEON)
            settings_win.destroy()

        def on_language_changed(lang_label):
            lang_code = lang_label.lower()
            _collect_state()
            self.app_config["language"] = lang_code
            jh_storage_manager.save_config(self.app_config)
            jh_i18n.set_language(lang_code)
            self.retranslate_main_ui()
            settings_win.destroy()
            # Небольшая пауза: даём ОС закрыть старое окно до создания нового,
            # чтобы убрать двойное мигание при переключении языка.
            self.after(80, self.open_ai_settings_window)

        lang_seg.configure(command=on_language_changed)

        ctk.CTkButton(
            settings_win,
            text=tr("btn_save"),
            font=("Arial", 13, "bold"),
            fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK,
            height=40,
            command=save_and_close
        ).pack(pady=(5, 15), padx=30, fill="x")

        # ── Показ окна без единого мерцания ────────────────────────────────────
        # Порядок критичен на Windows:
        #   1. alpha=0  — окно «невидимо» при показе
        #   2. geometry — позиция без прыжка
        #   3. deiconify — создаёт HWND (нужен для iconbitmap)
        #   4. grab_set / focus_force
        #   5. after(50): iconbitmap (HWND гарантированно готов) + alpha=1
        # Вызов iconbitmap ДО deiconify всегда молча проваливается на Windows —
        # HWND CTkToplevel создаётся только при первом показе окна.
        def _show_window():
            if not settings_win.winfo_exists():
                return
            # 1. Скрываем через прозрачность, чтобы не было flash позиции
            try:
                settings_win.attributes("-alpha", 0.0)
            except Exception:
                pass
            # 2. Геометрия — центрируем относительно главного окна
            try:
                settings_win.update_idletasks()
                w, h = 450, 760
                try:
                    sc = settings_win._get_window_scaling()
                except Exception:
                    sc = 1.0
                # w/h логические → физические для арифметики; x/y остаются физическими
                child_phys_w, child_phys_h = w * sc, h * sc
                if self.winfo_exists():
                    px = self.winfo_rootx()
                    py = self.winfo_rooty()
                    pw = self.winfo_width()
                    ph = self.winfo_height()
                    x = int(px + (pw - child_phys_w) / 2)
                    y = int(py + (ph - child_phys_h) / 2)
                else:
                    x = int((settings_win.winfo_screenwidth() - child_phys_w) / 2)
                    y = int((settings_win.winfo_screenheight() - child_phys_h) / 2)
                settings_win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
            except Exception:
                settings_win.geometry("450x760")
            # 3. Показываем (прозрачное) — HWND теперь создан
            settings_win.deiconify()
            settings_win.grab_set()
            settings_win.focus_force()

            # 4. Иконка + восстановление непрозрачности после создания HWND
            def _finalize():
                if not settings_win.winfo_exists():
                    return
                try:
                    _apply_icon_win32(settings_win)
                except Exception:
                    pass
                try:
                    settings_win.attributes("-alpha", 1.0)
                except Exception:
                    pass
                settings_win.after(350, lambda: _apply_icon_win32(settings_win) if settings_win.winfo_exists() else None)
            settings_win.after(100, _finalize)

        settings_win.after(120, _show_window)

    def load_config_to_ui(self):
        """Загружает сохраненные настройки пользователя в основные поля UI при запуске."""
        self.first_name_input.delete(0, "end")
        self.first_name_input.insert(0, self.app_config.get("first_name", ""))
        
        self.last_name_input.delete(0, "end")
        self.last_name_input.insert(0, self.app_config.get("last_name", ""))
        
        self.resume_input.delete("0.0", "end")
        self.resume_input.insert("0.0", self.app_config.get("resume", ""))
        
        if not self.app_config.get("filter_remote", True): self.cb_remote.deselect()
        if self.app_config.get("filter_office", False): self.cb_office.select()
        if self.app_config.get("filter_hybrid", False): self.cb_hybrid.select()
        if not self.app_config.get("filter_location", True): self.cb_location.deselect()
        user_loc = self.app_config.get("user_location", "")
        if user_loc:
            self.location_entry.delete(0, "end")
            self.location_entry.insert(0, user_loc)

        provider = self.app_config.get("current_provider", "Gemini")
        if provider in LOCAL_PROVIDERS:
            self._local_server_ok = False
            self.update_local_server_status(provider)
        else:
            self._local_server_ok = True
            self.set_cloud_provider_status(provider)

    def save_current_config(self):
        """Синхронизирует текущие введенные настройки UI с конфигом и пишет их на диск."""
        self.app_config["first_name"] = self.first_name_input.get().strip()
        self.app_config["last_name"] = self.last_name_input.get().strip()
        self.app_config["resume"] = self.resume_input.get("0.0", "end-1c").strip()
        self.app_config["filter_remote"] = bool(self.cb_remote.get())
        self.app_config["filter_office"] = bool(self.cb_office.get())
        self.app_config["filter_hybrid"] = bool(self.cb_hybrid.get())
        self.app_config["filter_location"] = bool(self.cb_location.get())
        self.app_config["user_location"] = self.location_entry.get().strip()
        
        jh_storage_manager.save_config(self.app_config)

    def set_inputs_state(self, state):
        """Управляет доступностью полей конфигурации во время работы ассистента."""
        self.first_name_input.configure(state=state)
        self.last_name_input.configure(state=state)
        self.resume_input.configure(state=state)
        self.btn_paste_resume.configure(state=state)
        self.btn_history.configure(state=state)
        self.btn_pdf_import.configure(state=state)
        self.btn_ai_settings.configure(state=state)
        self.cb_remote.configure(state=state)
        self.cb_office.configure(state=state)
        self.cb_hybrid.configure(state=state)
        self.cb_location.configure(state=state)
        self.location_entry.configure(state=state)

    def _set_show_local_warning_async(self, value):
        """Асинхронно сохраняет флаг предупреждения о локальных LLM без блокировки UI."""
        def _bg():
            try:
                jh_storage_manager.set_show_local_warning(value)
            except Exception as e:
                print(f"[Config]: Не удалось сохранить флаг предупреждения: {e}")
        threading.Thread(target=_bg, daemon=True).start()

    def toggle_assistant(self):
        """Включает/выключает прием вебхуков и работу ИИ."""
        if not self.is_active:
            # app_config актуален: обновляется при save_and_close() настроек
            # и при process_incoming_vacancy() в фоне.
            # Повторное load_config() с диска здесь избыточно и блокирует GUI.
            provider = self.app_config.get("current_provider", "Gemini")
            model_pool = self.app_config.get("active_models", {}).get(provider, [])
            first_name = self.first_name_input.get().strip()

            if not model_pool:
                messagebox.showerror(
                    tr("err_start_title"),
                    tr("err_no_model_msg", provider=provider),
                    parent=self
                )
                return

            if provider in LOCAL_PROVIDERS:
                if not self._local_server_ok:
                    messagebox.showerror(
                        tr("err_start_title"),
                        tr("err_server_msg", provider=provider),
                        parent=self
                    )
                    return
            else:
                api_key = self.app_config.get("api_keys", {}).get(provider, "").strip()
                if not api_key or api_key == "local":
                    messagebox.showerror(
                        tr("err_start_title"),
                        tr("err_key_msg", provider=provider),
                        parent=self
                    )
                    return

            if not first_name:
                messagebox.showerror(
                    tr("err_start_title"),
                    tr("err_name_msg"),
                    parent=self
                )
                return

            was_paused = self._paused_mode
            self._paused_mode = False
            if not was_paused:
                # Reset session counters only on a fresh start (not resume)
                self._session_processed = 0
                self._session_approved = 0
                self._session_rejected = 0

            self.save_current_config()
            self.set_inputs_state("disabled")
            self._show_normal_toggle()

            if not was_paused:
                while not self.vacancy_queue.empty():
                    try:
                        self.vacancy_queue.get_nowait()
                    except queue.Empty:
                        break

            self.stop_worker_event.clear()
            self.worker_thread = threading.Thread(target=self.queue_worker_loop, daemon=True)
            self.worker_thread.start()

            if not self.server_started:
                self.server_started = True
                self._flask_ready.clear()  # reset in case of restart
                self.flask_thread = threading.Thread(target=self.run_flask_server, daemon=True)
                self.flask_thread.start()
                # Flask needs time to kill zombie processes (netstat + taskkill) and bind.
                # Keep is_active=False and show "starting" until _flask_ready is set.
                # This prevents ERR_CONNECTION_REFUSED during the startup window.
                self.btn_toggle.configure(text=tr("btn_starting"), state="disabled",
                                          fg_color=COLOR_GOLD, hover_color=COLOR_GOLD_HOVER,
                                          text_color=COLOR_BG_DARK)
                self.status_lbl.configure(text=tr("status_starting"), text_color=COLOR_GOLD)
                self.after(100, lambda: self._activate_when_ready(0))
            else:
                # Flask is already running (stop → start cycle or resume).
                self.is_active = True
                self.btn_toggle.configure(text=tr("btn_stop"), fg_color=COLOR_RED,
                                          hover_color=COLOR_RED_HOVER, text_color=COLOR_TEXT_LIGHT)
                self.status_lbl.configure(text=tr("status_active"), text_color=COLOR_CYAN_NEON)
        else:
            self.is_active = False
            self.stop_worker_event.set()
            self.set_inputs_state("normal")
            self._show_normal_toggle()
            self.status_lbl.configure(text=tr("status_stopped"), text_color=COLOR_RED)

            # _worker_has_item is True while the worker holds a dequeued item.
            # It sets the flag to False before returning (restoring item to queue).
            # We check both queue size and the flag to get the true pending count.
            q_size = self.vacancy_queue.qsize() + (1 if self._worker_has_item else 0)
            if q_size > 0:
                self._show_paused_toggle(q_size)
                self.status_lbl.configure(text=tr("status_paused", q=q_size), text_color=COLOR_GOLD)

    def kill_process_on_port(self, port):
        """Принудительно завершает процесс, занимающий указанный порт (работает на Windows)."""
        try:
            import subprocess
            import os
            cmd = f'netstat -ano | findstr :{port}'
            output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
            pids = set()
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and f":{port}" in parts[1]:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        pids.add(int(pid))
            for pid in pids:
                print(f"[Система]: Обнаружен зомби-процесс {pid} на порту {port}. Принудительно завершаем...")
                subprocess.run(f'taskkill /F /PID {pid}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[Система]: Не удалось очистить порт {port}: {e}")

    def run_flask_server(self):
        """
        Запускает Flask через werkzeug make_server в управляемом режиме.
        Хранит дескриптор сервера (self.flask_server), что позволяет позже
        корректно завершить его (shutdown) и не плодить висящие потоки/сокеты.
        """
        port = 5000
        self.kill_process_on_port(port)
        try:
            # make_server даёт объект сервера, которым можно управлять,
            # в отличие от flask_app.run(), который блокирует поток без выхода.
            from werkzeug.serving import make_server
            self.flask_server = make_server("127.0.0.1", port, flask_app, threaded=True)
            # Socket is bound and listening — safe to accept connections.
            self._flask_ready.set()
            print(f"[Flask]: Сервер запущен на 127.0.0.1:{port}")
            # serve_forever блокирует ЭТОТ поток до вызова shutdown().
            self.flask_server.serve_forever()
            print("[Flask]: Сервер штатно остановлен.")
        except OSError as e:
            print(f"[Flask Ошибка]: Не удалось привязать сокет к порту {port}: {e}")
            self.update_status(tr("status_server_fail", port=port), COLOR_RED)
            self.server_started = False
        except Exception as e:
            print(f"[Flask Ошибка]: Непредвиденный сбой веб-сервера ({type(e).__name__}): {e}")
            self.server_started = False

    def shutdown_flask_server(self):
        """Корректно останавливает werkzeug-сервер и дожидается завершения потока."""
        server = self.flask_server
        if server is not None:
            try:
                server.shutdown()      # разблокирует serve_forever
            except Exception as e:
                print(f"[Flask]: Ошибка при остановке сервера: {e}")
            try:
                server.server_close()  # закрывает слушающий сокет
            except Exception as e:
                print(f"[Flask]: Ошибка при закрытии сокета: {e}")
            self.flask_server = None
        thread = self.flask_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self.flask_thread = None
        self.server_started = False

    def update_status(self, text, color):
        """Безопасное обновление статуса на главном экране из фоновых потоков."""
        try:
            if self.winfo_exists():
                self.after(0, lambda: self.status_lbl.configure(text=text, text_color=color))
        except Exception as e:
            print(f"[Thread Status Error]: {e}")

    def _activate_when_ready(self, attempt):
        """Checks _flask_ready Event (set by run_flask_server after make_server binds).
        Non-blocking: threading.Event.is_set() returns instantly, no I/O on main thread."""
        if self.is_active:
            return
        if self._flask_ready.is_set():
            self.is_active = True
            self.btn_toggle.configure(text=tr("btn_stop"), state="normal",
                                      fg_color=COLOR_RED, hover_color=COLOR_RED_HOVER,
                                      text_color=COLOR_TEXT_LIGHT)
            self.status_lbl.configure(text=tr("status_active"), text_color=COLOR_CYAN_NEON)
        elif attempt < 60:  # wait up to 6 seconds (60 × 100ms)
            self.after(100, lambda a=attempt: self._activate_when_ready(a + 1))
        else:
            # Flask never came up — restore Start button
            self.is_active = False
            self.server_started = False
            self.set_inputs_state("normal")
            self._show_normal_toggle()
            self.status_lbl.configure(text=tr("status_server_fail", port=5000), text_color=COLOR_RED)

    def _safe_after(self, ms, callback):
        """
        Потокобезопасная обёртка над after(): проверяет существование окна
        перед постановкой коллбэка в Tcl-очередь.
        Используется из фоновых потоков вместо прямого self.after().
        """
        try:
            if self.winfo_exists():
                self.after(ms, callback)
        except Exception:
            pass

    def enqueue_vacancy(self, data):
        """
        Добавляет вакансию в очередь. Намеренно без локов — queue.Queue.put()
        потокобезопасен сам по себе. O(1) проверка дублей через _url_lock
        (удерживается микросекунды, никакого I/O). Финальная проверка дублей
        выполняется воркером перед обработкой — ловит редкие гонки.
        """
        url = data.get("url", "")
        if url and url != "#":
            if (jh_storage_manager.vacancy_url_in_approved(url) or
                    jh_storage_manager.vacancy_url_in_rejected(url)):
                self.update_status(tr("status_duplicate_db"), COLOR_TEXT_MUTED)
                return
        self._batch_id += 1
        self.vacancy_queue.put(data)
        q_size = self.vacancy_queue.qsize() + (1 if self._worker_has_item else 0)
        self.update_status(tr("status_queue_added", q=q_size), COLOR_GOLD)

    def queue_worker_loop(self):
        """Фоновый цикл обработки очереди с динамической задержкой из настроек."""
        while not self.stop_worker_event.is_set():
            try:
                vacancy_data = self.vacancy_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self._worker_has_item = True
            delay_seconds = self.app_config.get("request_delay", 15)

            if delay_seconds == 0:
                # No countdown — but still show queue status and check stop event
                current_q_size = self.vacancy_queue.qsize() + 1
                self.update_status(
                    tr("status_queue", sec=0, q=current_q_size, done=self._session_processed),
                    COLOR_GOLD
                )
                if self.stop_worker_event.is_set():
                    self.vacancy_queue.put(vacancy_data)
                    self._worker_has_item = False
                    return
            else:
                for remaining in range(delay_seconds, 0, -1):
                    current_q_size = self.vacancy_queue.qsize() + 1
                    self.update_status(
                        tr("status_queue", sec=remaining, q=current_q_size, done=self._session_processed),
                        COLOR_GOLD
                    )
                    # Проверяем stop каждые 200 мс — при остановке возвращаем элемент в очередь
                    # до того, как главный поток посчитает её размер.
                    for _ in range(5):
                        if self.stop_worker_event.is_set():
                            self.vacancy_queue.put(vacancy_data)
                            self._worker_has_item = False
                            return
                        time.sleep(0.2)

            if not self.stop_worker_event.is_set():
                # Worker-side dedup: catches the rare race where two concurrent
                # Flask threads both passed the enqueue_vacancy check before
                # either vacancy was saved. O(1), no I/O.
                url = vacancy_data.get("url", "")
                if url and url != "#" and (
                    jh_storage_manager.vacancy_url_in_approved(url) or
                    jh_storage_manager.vacancy_url_in_rejected(url)
                ):
                    self.vacancy_queue.task_done()
                    self._worker_has_item = False
                    continue

                self.process_incoming_vacancy(vacancy_data)
                self.vacancy_queue.task_done()

                # Debounced "queue done" notification: fires only if no new vacancy arrives within 2s.
                # _batch_id is incremented by enqueue_vacancy; the closure captures current value
                # and compares at fire time — if mismatch, a newer batch is in progress.
                if self.vacancy_queue.empty():
                    captured_batch = self._batch_id
                    def _deferred_notif(batch=captured_batch):
                        if (self._batch_id == batch
                                and self.vacancy_queue.empty()
                                and not self._worker_has_item
                                and self.is_active
                                and self.app_config.get("notifications_enabled", True)):
                            try:
                                import jh_notifications
                                jh_notifications.send_notification(
                                    "Job Hunter AI",
                                    tr("notif_queue_done",
                                       approved=self._session_approved,
                                       rejected=self._session_rejected),
                                    root=self
                                )
                            except Exception:
                                pass
                    # _safe_after проверяет существование окна перед after() из фонового потока
                    self._safe_after(2000, _deferred_notif)
            self._worker_has_item = False

    def process_incoming_vacancy(self, vacancy_data):
        """Обработка одной вакансии через ИИ-движок"""
        self.update_status(tr("status_analyzing"), COLOR_GOLD)
        self.app_config = jh_storage_manager.load_config()
        jh_i18n.set_language(self.app_config.get("language", "en"))

        try:
            status, result_text, extracted_info = jh_ai_engine.analyze_and_generate(vacancy_data, self.app_config)
            
            company = extracted_info.get("company", vacancy_data.get("company", "Не указана"))
            title = extracted_info.get("title", vacancy_data.get("title", "Не указано"))
            url = vacancy_data.get("url", "#")
            description = vacancy_data.get("text", "")

            if status == "APPROVED":
                jh_storage_manager.save_approved_vacancy(
                    company=company,
                    title=title,
                    url=url,
                    cover_letter=result_text,
                    description=description
                )
                self._session_approved += 1
                self._session_processed += 1
                self.update_status(tr("status_approved", title=title, company=company), COLOR_CYAN_NEON)
            elif status == "REJECTED":
                jh_storage_manager.save_rejected_vacancy(
                    company=company,
                    title=title,
                    url=url,
                    reason=result_text
                )
                self._session_rejected += 1
                self._session_processed += 1
                self.update_status(tr("status_rejected", title=title, company=company), COLOR_RED)
            else:
                self.update_status(tr("status_error", msg=result_text), COLOR_RED)
        except Exception as e:
            self.update_status(tr("status_proc_error", msg=str(e)), COLOR_RED)
            if self.app_config.get("notifications_enabled", True):
                try:
                    import jh_notifications
                    jh_notifications.send_notification("Job Hunter AI", tr("notif_error_body"), root=self)
                except Exception:
                    pass

    def import_resume_from_pdf(self):
        """Парсит PDF резюме, дистиллирует через ИИ и вставляет результат в поле опыта."""
        filepath = filedialog.askopenfilename(
            parent=self,
            title=tr("btn_pdf_import"),
            filetypes=[("PDF files", "*.pdf")]
        )
        if not filepath:
            return

        self.update_status(tr("pdf_processing"), COLOR_GOLD)
        self.btn_pdf_import.configure(state="disabled")

        def _worker():
            try:
                from pypdf import PdfReader
                try:
                    reader = PdfReader(filepath)
                except Exception:
                    self.after(0, lambda: self.update_status(tr("pdf_error_damaged"), COLOR_RED))
                    self.after(0, lambda: self.btn_pdf_import.configure(state="normal"))
                    return

                pages_text = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
                raw_text = "\n".join(pages_text).strip()

                if not raw_text:
                    self.after(0, lambda: self.update_status(tr("pdf_error_no_text"), COLOR_RED))
                    self.after(0, lambda: self.btn_pdf_import.configure(state="normal"))
                    return

                config = jh_storage_manager.load_config()
                distilled = jh_ai_engine.distill_resume(raw_text, config)

                def _apply():
                    self.resume_input.delete("0.0", "end")
                    self.resume_input.insert("0.0", distilled.strip())
                    self.update_status(tr("status_loaded"), COLOR_CYAN_NEON)
                    self.btn_pdf_import.configure(state="normal")

                self.after(0, _apply)

            except jh_ai_engine.AIEngineError as e:
                msg = e.detail
                self.after(0, lambda m=msg: self.update_status(tr("pdf_error_ai", msg=m), COLOR_RED))
                self.after(0, lambda: self.btn_pdf_import.configure(state="normal"))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self.update_status(tr("pdf_error_ai", msg=m), COLOR_RED))
                self.after(0, lambda: self.btn_pdf_import.configure(state="normal"))

        threading.Thread(target=_worker, daemon=True).start()

    def open_resume_history(self):
        """Popup window for saving / loading / deleting named resumes."""
        hist_win = ctk.CTkToplevel(self)
        hist_win.withdraw()
        hist_win.title(tr("history_win_title"))
        hist_win.configure(fg_color=COLOR_BG_DARK)
        force_dark_title_bar(hist_win)

        def _refresh(scroll_frame):
            for w in scroll_frame.winfo_children():
                w.destroy()
            history = jh_storage_manager.get_resume_history()
            if not history:
                ctk.CTkLabel(
                    scroll_frame,
                    text=tr("history_empty"),
                    font=("Arial", 12),
                    text_color=COLOR_TEXT_MUTED
                ).pack(pady=20)
                return
            for item in history:
                name = item.get("name", "")
                text = item.get("text", "")
                row = ctk.CTkFrame(scroll_frame, fg_color=COLOR_CARD_BG, corner_radius=6)
                row.pack(fill="x", padx=8, pady=3)
                ctk.CTkLabel(
                    row,
                    text=name,
                    font=("Arial", 12, "bold"),
                    text_color=COLOR_TEXT_LIGHT,
                    anchor="w"
                ).pack(side="left", padx=12, pady=8, fill="x", expand=True)

                def _load(t=text):
                    self.resume_input.delete("0.0", "end")
                    self.resume_input.insert("0.0", t)
                    hist_win.destroy()

                ctk.CTkButton(
                    row,
                    text=tr("history_btn_load"),
                    width=65,
                    height=28,
                    font=("Arial", 11, "bold"),
                    fg_color=COLOR_CYAN_NEON,
                    hover_color=COLOR_CYAN_HOVER,
                    text_color=COLOR_BG_DARK,
                    command=_load
                ).pack(side="right", padx=(4, 4), pady=6)

                def _delete(n=name, sf=scroll_frame):
                    jh_storage_manager.delete_resume_from_history(n)
                    _refresh(sf)

                ctk.CTkButton(
                    row,
                    text=tr("history_btn_delete"),
                    width=30,
                    height=28,
                    font=("Arial", 11, "bold"),
                    fg_color=COLOR_RED,
                    hover_color=COLOR_RED_HOVER,
                    text_color=COLOR_TEXT_LIGHT,
                    command=_delete
                ).pack(side="right", padx=(0, 4), pady=6)

        # Title with logo
        hist_header = ctk.CTkFrame(hist_win, fg_color="transparent")
        hist_header.pack(pady=(15, 8), padx=20)
        hist_logo = self.load_and_resize_logo(22)
        if hist_logo:
            ctk.CTkLabel(hist_header, image=hist_logo, text="").pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            hist_header,
            text=tr("history_win_title"),
            font=("Arial", 14, "bold"),
            text_color=COLOR_CYAN_NEON
        ).pack(side="left")

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(
            hist_win,
            fg_color=COLOR_BG_DARK,
            height=240
        )
        scroll.pack(fill="x", padx=12, pady=(0, 8))
        _refresh(scroll)

        # Separator
        ctk.CTkFrame(hist_win, height=1, fg_color=COLOR_CARD_BG).pack(fill="x", padx=12, pady=4)

        # Save section
        save_frame = ctk.CTkFrame(hist_win, fg_color="transparent")
        save_frame.pack(fill="x", padx=12, pady=(4, 15))

        name_entry = ctk.CTkEntry(
            save_frame,
            placeholder_text=tr("history_save_name_ph"),
            height=34,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT,
            placeholder_text_color=COLOR_TEXT_MUTED,
            font=("Arial", 11)
        )
        name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _save_current():
            name = name_entry.get().strip()
            if not name:
                self.update_status(tr("history_name_empty"), COLOR_GOLD)
                return
            current_text = self.resume_input.get("0.0", "end-1c").strip()
            # Check overwrite
            existing = [r.get("name") for r in jh_storage_manager.get_resume_history()]
            if name in existing:
                ok = messagebox.askyesno(
                    tr("history_win_title"),
                    tr("history_overwrite_q", name=name),
                    parent=hist_win
                )
                if not ok:
                    return
            jh_storage_manager.save_resume_to_history(name, current_text)
            _refresh(scroll)
            name_entry.delete(0, "end")

        ctk.CTkButton(
            save_frame,
            text=tr("history_btn_save"),
            height=34,
            font=("Arial", 11, "bold"),
            fg_color=COLOR_GOLD,
            hover_color=COLOR_GOLD_HOVER,
            text_color=COLOR_BG_DARK,
            command=_save_current
        ).pack(side="right")

        def _show_hist():
            if not hist_win.winfo_exists(): return
            try:
                hist_win.attributes("-alpha", 0.0)
            except Exception: pass
            try:
                hist_win.update_idletasks()
                w, h = 460, 420
                try:
                    sc = hist_win._get_window_scaling()
                except Exception:
                    sc = 1.0
                # w/h логические → физические для арифметики; x/y остаются физическими
                child_phys_w, child_phys_h = w * sc, h * sc
                px = self.winfo_rootx()
                py = self.winfo_rooty()
                pw = self.winfo_width()
                ph = self.winfo_height()
                x = int(px + (pw - child_phys_w) / 2)
                y = int(py + (ph - child_phys_h) / 2)
                hist_win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
            except Exception:
                hist_win.geometry("460x420")
            hist_win.deiconify()
            hist_win.grab_set()
            hist_win.focus_force()
            def _fin():
                if not hist_win.winfo_exists(): return
                try:
                    _apply_icon_win32(hist_win)
                except Exception: pass
                try:
                    hist_win.attributes("-alpha", 1.0)
                except Exception: pass
                hist_win.after(350, lambda: _apply_icon_win32(hist_win) if hist_win.winfo_exists() else None)
            hist_win.after(100, _fin)
        hist_win.after(120, _show_hist)

    def open_results(self):
        """Открывает окно со списком одобренных ИИ вакансий"""
        jh_results_ui.open_window(self)

# =====================================================================
# СТАРТ ПРИЛОЖЕНИЯ
# =====================================================================
if __name__ == "__main__":
    app = JobHunterApp()
    app.mainloop()