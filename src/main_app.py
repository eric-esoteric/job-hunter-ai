# main_app.py
import os
import sys
import json
import threading
import queue
import time
import customtkinter as ctk
from tkinter import messagebox, filedialog
from PIL import Image
import jh_ai_engine
import jh_storage_manager
import jh_results_ui
import jh_url_utils
import jh_version
import jh_i18n
from jh_i18n import tr
from jh_log import get_logger

logger = get_logger(__name__)

# =====================================================================
# НАСТРОЙКА DPI И СИСТЕМНОГО ОКРУЖЕНИЯ Windows
# =====================================================================
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)

# Пути к конфигурации
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'Job Hunter AI')
os.makedirs(APPDATA_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

# Иконки — ищем рядом с main_app.py (и при сборке PyInstaller — рядом с .exe)
def _resolve_asset(name):
    """Locate a bundled asset regardless of frozen/development context."""
    src_dir    = os.path.dirname(os.path.abspath(__file__))
    root_dir   = os.path.dirname(src_dir)
    candidates = [
        os.path.join(src_dir, name),                          # src/<name>
        os.path.join(root_dir, name),                         # project root
        os.path.join(root_dir, "assets", name),               # assets/<name>
        os.path.join(os.path.dirname(sys.executable), name),  # next to python/exe
        os.path.join(sys._MEIPASS, name) if hasattr(sys, "_MEIPASS") else "",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return os.path.join(src_dir, name)

ICON_PATH     = _resolve_asset("icon.ico")
LOGO_PNG_PATH = _resolve_asset("logo.png")

# Инициализируем локальную БД
jh_storage_manager.init_db()

# Color palette — updated at runtime by apply_theme(); Cyber-Owl defaults shown
COLOR_BG_DARK    = "#0E1520"
COLOR_CARD_BG    = "#17202E"
COLOR_INPUT_BG   = "#0E1520"
COLOR_CYAN_NEON  = "#D4845A"
COLOR_CYAN_HOVER = "#7DC8D4"
COLOR_GOLD       = "#CFA554"
COLOR_GOLD_HOVER = "#B08A3C"
COLOR_RED        = "#C46870"
COLOR_RED_HOVER  = "#A55560"
COLOR_TEXT_MUTED = "#7A8899"
COLOR_TEXT_LIGHT = "#C8D4E0"

# ── Theme system ──────────────────────────────────────────────────────────────
LOCAL_SETTINGS_FILE = os.path.join(APPDATA_DIR, "local_settings.json")

THEMES = {
    "Cyber-Owl": {
        "bg":              "#0E1520",
        "card_bg":         "#17202E",
        "input_bg":        "#0E1520",
        "text":            "#C8D4E0",
        "text_muted":      "#7A8899",
        "accent":          "#D4845A",
        "accent_hover":    "#7DC8D4",
        "accent_text":     "#0E1520",
        "secondary_fg":    "#17202E",
        "secondary_hover": "#1F2E42",
        "secondary_text":  "#7DC8D4",
        "danger":          "#C46870",
        "danger_hover":    "#A55560",
        "gold":            "#CFA554",
        "gold_hover":      "#B08A3C",
        "corner_radius":   8,
        "fonts": {
            "title":    ("Arial", 24, "bold"),
            "subtitle": ("Arial", 12),
            "section":  ("Arial", 13, "bold"),
            "btn_lg":   ("Arial", 15, "bold"),
            "btn_md":   ("Arial", 13, "bold"),
            "btn_sm":   ("Arial", 11, "bold"),
        },
        "btn_primary_border":   0,
        "btn_secondary_border": 0,
        "btn_start_hover":      "#7DC8D4",
        "icon_hover":           "#1F2E42",
    },
    "Hotline Miami": {
        "bg":              "#000000",
        "card_bg":         "#1A0022",
        "input_bg":        "#1A0022",
        "text":            "#00F0FF",
        "text_muted":      "#00A0AA",
        "accent":          "#E500FF",
        "accent_hover":    "#00F0FF",
        "accent_text":     "#000000",
        "secondary_fg":    "#000000",
        "secondary_hover": "#E500FF",
        "secondary_text":  "#FF5E00",
        "danger":          "#E500FF",
        "danger_hover":    "#FF5E00",
        "gold":            "#FF5E00",
        "gold_hover":      "#E500FF",
        "corner_radius":   0,
        "fonts": {
            "title":    ("Courier New", 24, "bold"),
            "subtitle": ("Courier New", 12, "bold"),
            "section":  ("Courier New", 13, "bold"),
            "btn_lg":   ("Courier New", 15, "bold"),
            "btn_md":   ("Courier New", 13, "bold"),
            "btn_sm":   ("Courier New", 11, "bold"),
        },
        "btn_primary_border":   2,
        "btn_secondary_border": 2,
        "btn_start_hover":      "#C800DD",
        "icon_hover":           "#280038",
    },
}


def load_theme_config() -> str:
    """Returns the saved theme name, defaulting to 'Cyber-Owl'."""
    try:
        if os.path.exists(LOCAL_SETTINGS_FILE):
            with open(LOCAL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f).get("theme", "Cyber-Owl")
                return saved if saved in THEMES else "Cyber-Owl"
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
    return "Cyber-Owl"


def save_theme_config(theme_name: str) -> None:
    """Persists the chosen theme to local_settings.json (atomic write)."""
    try:
        data: dict = {}
        if os.path.exists(LOCAL_SETTINGS_FILE):
            try:
                with open(LOCAL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["theme"] = theme_name
        import tempfile as _tmp
        fd, tmp_path = _tmp.mkstemp(dir=APPDATA_DIR, prefix="ls_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            os.replace(tmp_path, LOCAL_SETTINGS_FILE)
        except Exception:
            try:
                os.remove(tmp_path)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
    except Exception as exc:
        logger.error(f"[Theme]: save error: {exc}")

# Доступные модели по провайдерам
ALL_PROVIDERS_MODELS = {
    "Gemini":    ["gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3.0-pro"],
    "OpenAI":    ["gpt-5-mini", "gpt-5", "o3-mini"],
    "Anthropic": ["claude-4-haiku", "claude-4-sonnet", "claude-4-opus"],
    "DeepSeek":  ["deepseek-chat", "deepseek-reasoner"],
    # OpenRouter aggregates many vendors behind one OpenAI-compatible API;
    # models are addressed as "vendor/model".
    "OpenRouter": ["openai/gpt-5-mini", "anthropic/claude-4-sonnet",
                   "google/gemini-3.5-flash", "deepseek/deepseek-chat"],
    "Ollama":    ["local-model"],
    "LM Studio": ["local-model"],
}
LOCAL_PROVIDERS = ("Ollama", "LM Studio")
PROVIDER_ORDER  = ["Gemini", "OpenAI", "Anthropic", "DeepSeek", "OpenRouter", "Ollama", "LM Studio"]

# Optional tray support
try:
    import pystray as _pystray
    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False

# =====================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ИНТЕРФЕЙСА
# =====================================================================
def force_dark_title_bar(window):
    """Принудительно перекрашивает заголовок окна Windows в тёмный цвет."""
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if hwnd == 0:
            hwnd = window.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)


def _apply_icon_win32(window):
    """Sets window icon via Tkinter + Win32 API for reliable CTkToplevel support."""
    if not os.path.exists(ICON_PATH):
        return
    try:
        window.iconbitmap(ICON_PATH)
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
    try:
        import ctypes
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
        logger.debug("Suppressed exception", exc_info=True)


def center_window(window, width, height, parent=None):
    """Centres a window without flicker: alpha=0 → geometry → alpha=1."""
    try:
        window.attributes("-alpha", 0.0)
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)

    def _apply():
        if not window.winfo_exists():
            return
        try:
            window.update_idletasks()
            try:
                sc = window._get_window_scaling()
            except Exception:
                sc = 1.0
            pw_phys = width  * sc
            ph_phys = height * sc
            if parent and parent.winfo_exists():
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                x = int(px + (pw - pw_phys) / 2)
                y = int(py + (ph - ph_phys) / 2)
            else:
                sw = window.winfo_screenwidth()
                sh = window.winfo_screenheight()
                x = int((sw - pw_phys) / 2)
                y = int((sh - ph_phys) / 2)
            window.geometry(f"{width}x{height}+{max(0,x)}+{max(0,y)}")
        except Exception:
            window.geometry(f"{width}x{height}")
        finally:
            try:
                window.attributes("-alpha", 1.0)
                window.deiconify()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

    window.after(15, _apply)


def bind_russian_hotkeys(widget):
    """Ctrl+C/V/A/X support for Russian keyboard layouts."""
    target = widget
    if hasattr(widget, "_entry"):
        target = widget._entry
    elif hasattr(widget, "_textbox"):
        target = widget._textbox

    def _handle(event):
        key     = event.keysym.lower()
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
                        logger.debug("Suppressed exception", exc_info=True)
                event.widget.insert("insert", text)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            return "break"

        elif keycode == 67 or key in ('c', 'cyrillic_es'):
            try:
                sel = None
                try:
                    sel = event.widget.get("sel.first", "sel.last")
                except Exception:
                    try:
                        sel = event.widget.selection_get()
                    except Exception:
                        logger.debug("Suppressed exception", exc_info=True)
                if sel:
                    event.widget.clipboard_clear()
                    event.widget.clipboard_append(sel)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
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
                logger.debug("Suppressed exception", exc_info=True)
            return "break"

        elif keycode == 88 or key in ('x', 'cyrillic_che'):
            try:
                sel = None
                try:
                    sel = event.widget.get("sel.first", "sel.last")
                    if sel:
                        event.widget.clipboard_clear()
                        event.widget.clipboard_append(sel)
                        event.widget.delete("sel.first", "sel.last")
                except Exception:
                    try:
                        sel = event.widget.selection_get()
                        if sel:
                            event.widget.clipboard_clear()
                            event.widget.clipboard_append(sel)
                            event.widget.delete("sel.first", "sel.last")
                    except Exception:
                        logger.debug("Suppressed exception", exc_info=True)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            return "break"

    try:
        target.bind("<Control-KeyPress>", _handle)
    except Exception as e:
        logger.error(f"[Hotkeys]: bind error: {e}")


# =====================================================================
# АДАПТЕР ОЧЕРЕДИ
# =====================================================================
class _EnqueueAdapter:
    """
    Thin shim handed to BrowserCaptureEngine in place of the raw queue.

    The engine only ever calls .put(payload); routing that through
    JobHunterApp.enqueue_vacancy restores pre-queue dedup, _batch_id tracking,
    and the "added to queue" status feedback (all previously dead because the
    engine wrote to the queue directly).
    """
    __slots__ = ("_app",)

    def __init__(self, app):
        self._app = app

    def put(self, data, *args, **kwargs):
        self._app.enqueue_vacancy(data)


# =====================================================================
# ГЛАВНЫЙ ИНТЕРФЕЙС ПРИЛОЖЕНИЯ
# =====================================================================
class JobHunterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.is_active      = False
        self._paused_mode   = False
        self._btn_resume    = None
        self._btn_reset     = None
        self._worker_has_item       = False
        self._batch_id              = 0
        self._local_server_ok       = False
        self._server_poll_after_id  = None
        self._session_processed     = 0
        self._session_approved      = 0
        self._session_rejected      = 0
        self._tray_icon             = None

        # Потокобезопасная очередь вакансий
        self.vacancy_queue     = queue.Queue()
        self.worker_thread     = None
        self.stop_worker_event = threading.Event()

        # Lifecycle flag: set while the Tkinter main loop is alive.
        # Background threads check this instead of calling winfo_exists() —
        # winfo_exists() is a Tkinter call that must only run on the main thread.
        self._alive = threading.Event()
        self._alive.set()

        # Загружаем конфигурацию и применяем язык интерфейса
        self.app_config = jh_storage_manager.load_config()
        jh_i18n.set_language(self.app_config.get("language", "en"))

        # Load saved theme and update global color palette before any widget is created
        self._active_theme = load_theme_config()
        self._tw = {}
        _t = THEMES[self._active_theme]
        global COLOR_BG_DARK, COLOR_CARD_BG, COLOR_INPUT_BG
        global COLOR_CYAN_NEON, COLOR_CYAN_HOVER, COLOR_GOLD, COLOR_GOLD_HOVER
        global COLOR_RED, COLOR_RED_HOVER, COLOR_TEXT_MUTED, COLOR_TEXT_LIGHT
        COLOR_BG_DARK    = _t["bg"];      COLOR_CARD_BG    = _t["card_bg"]
        COLOR_INPUT_BG   = _t["input_bg"]
        COLOR_CYAN_NEON  = _t["accent"];  COLOR_CYAN_HOVER = _t["accent_hover"]
        COLOR_GOLD       = _t["gold"];    COLOR_GOLD_HOVER = _t["gold_hover"]
        COLOR_RED        = _t["danger"];  COLOR_RED_HOVER  = _t["danger_hover"]
        COLOR_TEXT_MUTED = _t["text_muted"]; COLOR_TEXT_LIGHT = _t["text"]

        try:
            import jh_notifications
            jh_notifications.apply_theme(_t)
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

        self.title(jh_version.get_window_title())
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG_DARK)
        ctk.set_appearance_mode("dark")

        center_window(self, 680, 790)
        force_dark_title_bar(self)

        # WM_DELETE_WINDOW → скрываем в трей вместо завершения
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        try:
            if os.path.exists(ICON_PATH):
                self.iconbitmap(ICON_PATH)
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

        self.setup_ui()
        self.load_config_to_ui()

        # Запускаем движок захвата (глобальная горячая клавиша всегда активна;
        # данные принимаются только когда is_active == True).
        self._init_automation()

    # ── Automation ────────────────────────────────────────────────────────────

    def _init_automation(self) -> None:
        """Creates and starts the BrowserCaptureEngine in a daemon thread."""
        try:
            from jh_automation import BrowserCaptureEngine, HotkeySpec
            spec = HotkeySpec.from_config(self.app_config)
            # Route every engine payload through enqueue_vacancy (pre-queue dedup,
            # batch-id tracking, status feedback) instead of letting the engine
            # push straight into the raw queue. The adapter exposes only .put(),
            # the sole queue method the engine uses.
            self._automation = BrowserCaptureEngine(
                vacancy_queue=_EnqueueAdapter(self),
                app_ready_fn=lambda: self.is_active,
                hotkey_spec=spec,
                notify_fn=self._make_hotkey_notify_fn(),
                capture_success_fn=self._make_capture_success_fn(),
            )
            self._automation.start()
        except Exception as exc:
            logger.error(f"[Automation]: Failed to initialise: {exc}")
            self._automation = None

    def _make_hotkey_notify_fn(self):
        """
        Returns a callable safe to invoke from the capture daemon thread.
        Updates the status bar via after() — no preemptive toast is shown here;
        the success toast fires only after verified content lands in the queue
        (see _make_capture_success_fn).
        """
        def _notify():
            # _ui_update runs on the main thread via after() — winfo_exists() is
            # safe there.  The outer guard uses _alive (no Tkinter call) because
            # _notify() itself is invoked from the automation daemon thread.
            def _ui_update():
                if not self._alive.is_set():
                    return
                if not self.is_active:
                    return
                self.update_status(tr("status_capturing"), COLOR_GOLD)
            if self._alive.is_set():
                try:
                    self.after(0, _ui_update)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
        return _notify

    def _make_capture_success_fn(self):
        """
        Returns a callable invoked by BrowserCaptureEngine after a vacancy
        payload has been verified and placed in the queue.  Fires a toast
        only at that point — after the capture is confirmed successful.
        Dispatched to the Tkinter thread via after() for thread safety.
        """
        def _on_success():
            def _ui():
                if not self._alive.is_set():
                    return
                if not self.app_config.get("notifications_enabled", True):
                    return
                try:
                    import jh_notifications
                    jh_notifications.send_notification(
                        "Job Hunter AI",
                        tr("notif_capture_success"),
                        root=self,
                        on_click=self._bring_to_front,
                        is_error=False,
                    )
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
            if self._alive.is_set():
                try:
                    self.after(0, _ui)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
        return _on_success

    # ── System tray ───────────────────────────────────────────────────────────

    def on_closing(self) -> None:
        """Hide the window to the system tray instead of terminating."""
        self.withdraw()
        self._start_tray_icon()

    def _start_tray_icon(self) -> None:
        """Creates a pystray icon and runs it in a daemon thread."""
        if not _TRAY_AVAILABLE:
            # No pystray — fall through to real exit
            self._do_exit()
            return

        # Stop any previous tray icon
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            self._tray_icon = None

        def _on_open(icon, _item):
            icon.stop()
            self._tray_icon = None
            try:
                self.after(0, self._restore_from_tray)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        def _on_exit(icon, _item):
            icon.stop()
            self._tray_icon = None
            try:
                self.after(0, self._do_exit)
            except Exception:
                self._do_exit()

        menu = _pystray.Menu(
            _pystray.MenuItem(tr("tray_open"), _on_open, default=True),
            _pystray.MenuItem(tr("tray_exit"), _on_exit),
        )

        # Load icon image for tray
        tray_img = None
        for path in (ICON_PATH, LOGO_PNG_PATH):
            if os.path.exists(path):
                try:
                    tray_img = Image.open(path).convert("RGBA")
                    tray_img = tray_img.resize((64, 64), Image.Resampling.LANCZOS)
                    break
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
        if tray_img is None:
            tray_img = Image.new("RGBA", (64, 64), (0, 216, 198, 255))

        icon = _pystray.Icon("JobHunterAI", tray_img, "Job Hunter AI", menu)
        self._tray_icon = icon

        t = threading.Thread(target=icon.run, daemon=True, name="TrayThread")
        t.start()

    def _restore_from_tray(self) -> None:
        """Restores the main window from the system tray."""
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            force_dark_title_bar(self)
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

    def _bring_to_front(self) -> None:
        """Brings the main window to the foreground; restores from tray if hidden."""
        icon, self._tray_icon = self._tray_icon, None
        if icon is not None:
            # Mirror _on_open: stop the icon fully first, then schedule restore.
            # Calling deiconify() while the tray icon's Win32 message loop is still
            # running prevents the window from reliably receiving foreground focus.
            def _stop_then_restore():
                icon.stop()
                if self._alive.is_set():
                    try:
                        self.after(0, self._restore_from_tray)
                    except Exception:
                        logger.debug("Suppressed exception", exc_info=True)
            threading.Thread(target=_stop_then_restore, daemon=True, name="TrayStop").start()
        else:
            self._restore_from_tray()

    def _do_exit(self) -> None:
        """Performs a clean, unconditional application exit."""
        self.is_active = False
        self.stop_worker_event.set()
        self._alive.clear()  # signal all background threads to stop posting UI updates

        if self._server_poll_after_id is not None:
            try:
                self.after_cancel(self._server_poll_after_id)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        automation = getattr(self, "_automation", None)
        if automation is not None:
            try:
                automation.stop()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        worker = getattr(self, "worker_thread", None)
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)

        os._exit(0)

    # ── Logo ──────────────────────────────────────────────────────────────────

    def load_and_resize_logo(self, height_pixels):
        """Loads and DPI-scales the logo for the given logical height."""
        try:
            try:
                scaling = self._get_window_scaling()
            except Exception:
                scaling = 1.0
            target_h = int(height_pixels * scaling)
            logo_img = None
            if os.path.exists(LOGO_PNG_PATH):
                logo_img = Image.open(LOGO_PNG_PATH)
            elif os.path.exists(ICON_PATH):
                logo_img = Image.open(ICON_PATH)
            if logo_img:
                aspect      = logo_img.width / logo_img.height
                target_w    = int(target_h * aspect)
                logo_img    = logo_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                return ctk.CTkImage(
                    light_image=logo_img, dark_image=logo_img,
                    size=(int(target_w / scaling), int(target_h / scaling))
                )
        except Exception as e:
            logger.warning(f"[Logo]: {e}")
        return None

    # ── Main UI ───────────────────────────────────────────────────────────────

    def setup_ui(self):
        """Builds all widgets in the main window."""
        self._tw = {
            "label_title":    [], "label_muted":    [], "label_body":      [],
            "frame_card":     [], "input":           [], "textbox":         [],
            "btn_primary_sm": [], "btn_gold":        [],
            "btn_accent_icon":[], "btn_gold_icon":   [], "btn_danger_icon": [],
            "checkbox":       [],
        }

        header_container = ctk.CTkFrame(self, fg_color="transparent")
        header_container.pack(pady=(20, 5))

        logo_image = self.load_and_resize_logo(38)
        if logo_image:
            ctk.CTkLabel(header_container, image=logo_image, text="").pack(side="left", padx=(0, 12))

        self._title_lbl = ctk.CTkLabel(
            header_container, text="JOB HUNTER AI",
            font=("Arial", 24, "bold"), text_color=COLOR_CYAN_NEON
        )
        self._title_lbl.pack(side="left")
        self._tw["label_title"].append(self._title_lbl)

        self._subtitle_lbl = ctk.CTkLabel(
            self, text=tr("subtitle"),
            font=("Arial", 12), text_color=COLOR_TEXT_MUTED
        )
        self._subtitle_lbl.pack(pady=(0, 20))
        self._tw["label_muted"].append(self._subtitle_lbl)

        name_frame = ctk.CTkFrame(self, fg_color="transparent")
        name_frame.pack(pady=10, padx=30, fill="x")

        self.first_name_input = ctk.CTkEntry(
            name_frame, placeholder_text=tr("first_name_ph"), height=45,
            fg_color=COLOR_INPUT_BG, border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT, placeholder_text_color=COLOR_TEXT_MUTED
        )
        self.first_name_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        bind_russian_hotkeys(self.first_name_input)

        self.last_name_input = ctk.CTkEntry(
            name_frame, placeholder_text=tr("last_name_ph"), height=45,
            fg_color=COLOR_INPUT_BG, border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT, placeholder_text_color=COLOR_TEXT_MUTED
        )
        self.last_name_input.pack(side="right", fill="x", expand=True, padx=(10, 0))
        bind_russian_hotkeys(self.last_name_input)
        self._tw["input"].extend([self.first_name_input, self.last_name_input])

        resume_header_frame = ctk.CTkFrame(self, fg_color="transparent")
        resume_header_frame.pack(anchor="w", padx=30, pady=(15, 5), fill="x")

        self._resume_lbl = ctk.CTkLabel(
            resume_header_frame, text=tr("resume_label"),
            font=("Arial", 13, "bold"), text_color=COLOR_TEXT_LIGHT
        )
        self._resume_lbl.pack(side="left")
        self._tw["label_body"].append(self._resume_lbl)

        def paste_to_resume():
            try:
                self.resume_input.delete("0.0", "end")
                self.resume_input.insert("0.0", self.clipboard_get().strip())
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        self.btn_ai_settings = ctk.CTkButton(
            resume_header_frame, text="⚙", width=30, height=30,
            font=("Arial", 14), fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_CYAN_NEON, border_width=1, border_color=COLOR_CYAN_NEON,
            command=self.open_ai_settings_window
        )
        self.btn_ai_settings.pack(side="right")
        self._tw["btn_accent_icon"].append(self.btn_ai_settings)

        self.btn_history = ctk.CTkButton(
            resume_header_frame, text="📂", width=30, height=30,
            font=("Arial", 14), fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_GOLD, border_width=1, border_color=COLOR_GOLD,
            command=self.open_resume_history
        )
        self.btn_history.pack(side="right", padx=(0, 4))
        self._tw["btn_gold_icon"].append(self.btn_history)

        self.btn_paste_resume = ctk.CTkButton(
            resume_header_frame, text="📋", width=30, height=30,
            font=("Arial", 14), fg_color=COLOR_CARD_BG, hover_color=COLOR_CARD_BG,
            text_color=COLOR_CYAN_NEON, border_width=1, border_color=COLOR_CYAN_NEON,
            command=paste_to_resume
        )
        self.btn_paste_resume.pack(side="right", padx=(0, 4))
        self._tw["btn_accent_icon"].append(self.btn_paste_resume)

        self.btn_pdf_import = ctk.CTkButton(
            resume_header_frame, text=tr("btn_pdf_import"),
            width=38, height=30, font=("Arial", 11, "bold"),
            fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_RED, border_width=1, border_color=COLOR_RED,
            command=self.import_resume_from_pdf
        )
        self.btn_pdf_import.pack(side="right", padx=(0, 4))
        self._tw["btn_danger_icon"].append(self.btn_pdf_import)

        self.resume_input = ctk.CTkTextbox(
            self, height=180, fg_color=COLOR_INPUT_BG, border_color=COLOR_CARD_BG,
            border_width=1, text_color=COLOR_TEXT_LIGHT
        )
        self.resume_input.pack(pady=5, padx=30, fill="x")
        bind_russian_hotkeys(self.resume_input)
        self._tw["textbox"].append(self.resume_input)

        self._filter_lbl = ctk.CTkLabel(
            self, text=tr("filter_label"),
            font=("Arial", 13, "bold"), text_color=COLOR_TEXT_LIGHT
        )
        self._filter_lbl.pack(anchor="w", padx=30, pady=(15, 5))
        self._tw["label_body"].append(self._filter_lbl)

        self._filter_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD_BG, corner_radius=8)
        self._filter_frame.pack(pady=5, padx=30, fill="x")
        self._tw["frame_card"].append(self._filter_frame)

        cb_kwargs = dict(
            text_color=COLOR_TEXT_LIGHT, fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER, border_color=COLOR_TEXT_MUTED,
            checkbox_width=20, checkbox_height=20, border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        )

        self.cb_remote = ctk.CTkCheckBox(self._filter_frame, text=tr("cb_remote"), **cb_kwargs)
        self.cb_remote.pack(side="left", padx=15, pady=12)
        self.cb_remote.select()

        self.cb_office = ctk.CTkCheckBox(self._filter_frame, text=tr("cb_office"), **cb_kwargs)
        self.cb_office.pack(side="left", padx=15, pady=12)

        self.cb_hybrid = ctk.CTkCheckBox(self._filter_frame, text=tr("cb_hybrid"), **cb_kwargs)
        self.cb_hybrid.pack(side="left", padx=15, pady=12)

        loc_frame = ctk.CTkFrame(self._filter_frame, fg_color="transparent")
        loc_frame.pack(side="right", padx=(0, 10), pady=8)

        self.cb_location = ctk.CTkCheckBox(loc_frame, text=tr("cb_location"), **cb_kwargs)
        self.cb_location.pack(side="left")
        self.cb_location.select()

        self.location_entry = ctk.CTkEntry(
            loc_frame, placeholder_text=tr("location_placeholder"),
            width=130, height=30, fg_color=COLOR_INPUT_BG, border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT, placeholder_text_color=COLOR_TEXT_MUTED,
            font=("Arial", 11)
        )
        self.location_entry.pack(side="left", padx=(8, 0))
        self._tw["checkbox"].extend([self.cb_remote, self.cb_office, self.cb_hybrid, self.cb_location])
        self._tw["input"].append(self.location_entry)

        def _reset_focus(event):
            self.focus()

        for cb in (self.cb_remote, self.cb_office, self.cb_hybrid, self.cb_location):
            cb.bind("<ButtonRelease-1>", _reset_focus)

        self.status_lbl = ctk.CTkLabel(
            self, text=tr("status_loaded"), font=("Arial", 12, "bold"),
            text_color=COLOR_CYAN_NEON, wraplength=600
        )
        self.status_lbl.pack(pady=10)

        self._toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._toggle_frame.pack(pady=5, padx=30, fill="x")
        self._show_normal_toggle()

        self._btn_results = ctk.CTkButton(
            self, text=tr("btn_results"),
            font=("Arial", 13, "bold"), fg_color=COLOR_GOLD, hover_color=COLOR_GOLD_HOVER,
            text_color=COLOR_BG_DARK, height=45, command=self.open_results
        )
        self._btn_results.pack(pady=(5, 20), padx=30, fill="x")
        self._tw["btn_gold"].append(self._btn_results)

    def retranslate_main_ui(self):
        """Updates all localisable strings after a language switch."""
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
            self.first_name_input.configure(placeholder_text=tr("first_name_ph"))
            self.last_name_input.configure(placeholder_text=tr("last_name_ph"))

            if self.is_active:
                try:
                    self.btn_toggle.configure(text=tr("btn_stop"))
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
            elif self._paused_mode:
                try:
                    self._btn_resume.configure(text=tr("btn_resume"))
                    self._btn_reset.configure(text=tr("btn_reset_queue"))
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
            else:
                try:
                    self.btn_toggle.configure(text=tr("btn_start"))
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
        except Exception as e:
            logger.error(f"[i18n]: retranslate_main_ui error: {e}")

    def _show_normal_toggle(self):
        for w in self._toggle_frame.winfo_children():
            w.destroy()
        _t   = THEMES.get(getattr(self, "_active_theme", "Cyber-Owl"), THEMES["Cyber-Owl"])
        _pbw = _t["btn_primary_border"]
        self.btn_toggle = ctk.CTkButton(
            self._toggle_frame, text=tr("btn_start"),
            font=_t["fonts"]["btn_lg"], fg_color=COLOR_CYAN_NEON,
            hover_color=_t.get("btn_start_hover", COLOR_CYAN_HOVER), text_color=COLOR_BG_DARK,
            height=50, corner_radius=_t["corner_radius"],
            border_width=_pbw,
            border_color=COLOR_CYAN_NEON if _pbw else COLOR_CARD_BG,
            command=self.toggle_assistant
        )
        self.btn_toggle.pack(fill="x")

    def _show_paused_toggle(self, q_size=0):
        self._paused_mode = True
        for w in self._toggle_frame.winfo_children():
            w.destroy()
        self._toggle_frame.columnconfigure(0, weight=4)
        self._toggle_frame.columnconfigure(1, weight=1)
        _t   = THEMES.get(getattr(self, "_active_theme", "Cyber-Owl"), THEMES["Cyber-Owl"])
        _pbw = _t["btn_primary_border"]
        _cr  = _t["corner_radius"]
        self._btn_resume = ctk.CTkButton(
            self._toggle_frame, text=tr("btn_resume"),
            font=_t["fonts"]["btn_lg"], fg_color=COLOR_CYAN_NEON,
            hover_color=_t.get("btn_start_hover", COLOR_CYAN_HOVER), text_color=COLOR_BG_DARK,
            height=50, corner_radius=_cr, border_width=_pbw,
            border_color=COLOR_CYAN_NEON if _pbw else COLOR_CARD_BG,
            command=self.toggle_assistant
        )
        self._btn_resume.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._btn_reset = ctk.CTkButton(
            self._toggle_frame, text=tr("btn_reset_queue"),
            font=_t["fonts"]["btn_md"], fg_color=COLOR_RED, hover_color=COLOR_RED_HOVER,
            text_color=COLOR_TEXT_LIGHT, height=50, corner_radius=_cr,
            command=self._reset_queue
        )
        self._btn_reset.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _reset_queue(self):
        while not self.vacancy_queue.empty():
            try:
                self.vacancy_queue.get_nowait()
            except queue.Empty:
                break
        self._paused_mode = False
        self._show_normal_toggle()
        self.status_lbl.configure(text=tr("status_stopped"), text_color=COLOR_RED)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def apply_theme(self, theme_name: str) -> None:
        """Switch the active theme and immediately repaint all registered widgets."""
        global COLOR_BG_DARK, COLOR_CARD_BG, COLOR_INPUT_BG
        global COLOR_CYAN_NEON, COLOR_CYAN_HOVER, COLOR_GOLD, COLOR_GOLD_HOVER
        global COLOR_RED, COLOR_RED_HOVER, COLOR_TEXT_MUTED, COLOR_TEXT_LIGHT

        if theme_name not in THEMES:
            theme_name = "Cyber-Owl"
        self._active_theme = theme_name
        t = THEMES[theme_name]

        COLOR_BG_DARK    = t["bg"];      COLOR_CARD_BG    = t["card_bg"]
        COLOR_INPUT_BG   = t["input_bg"]
        COLOR_CYAN_NEON  = t["accent"];  COLOR_CYAN_HOVER = t["accent_hover"]
        COLOR_GOLD       = t["gold"];    COLOR_GOLD_HOVER = t["gold_hover"]
        COLOR_RED        = t["danger"];  COLOR_RED_HOVER  = t["danger_hover"]
        COLOR_TEXT_MUTED = t["text_muted"]; COLOR_TEXT_LIGHT = t["text"]

        save_theme_config(theme_name)

        fonts = t["fonts"]
        cr    = t["corner_radius"]
        pbw   = t["btn_primary_border"]
        tw    = getattr(self, "_tw", {})

        try:
            self.configure(fg_color=t["bg"])
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("label_title", []):
            try:
                w.configure(text_color=t["accent"], font=fonts["title"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("label_muted", []):
            try:
                w.configure(text_color=t["text_muted"], font=fonts["subtitle"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("label_body", []):
            try:
                w.configure(text_color=t["text"], font=fonts["section"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("frame_card", []):
            try:
                w.configure(fg_color=t["card_bg"], corner_radius=cr)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("input", []):
            try:
                w.configure(fg_color=t["input_bg"], border_color=t["card_bg"],
                            text_color=t["text"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("textbox", []):
            try:
                w.configure(fg_color=t["input_bg"], border_color=t["card_bg"],
                            text_color=t["text"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("btn_primary_sm", []):
            try:
                w.configure(fg_color=t["accent"], hover_color=t["accent_hover"],
                            text_color=t["accent_text"], corner_radius=cr,
                            border_width=pbw,
                            border_color=t["accent"] if pbw else t["card_bg"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("btn_gold", []):
            try:
                w.configure(fg_color=t["gold"], hover_color=t["gold_hover"],
                            text_color=t["bg"], corner_radius=cr,
                            font=fonts["btn_md"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        _icon_hover = t.get("icon_hover", t["secondary_hover"])

        for w in tw.get("btn_accent_icon", []):
            try:
                w.configure(fg_color=t["card_bg"], hover_color=_icon_hover,
                            text_color=t["accent"], border_color=t["accent"],
                            corner_radius=cr)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("btn_gold_icon", []):
            try:
                w.configure(fg_color=t["card_bg"], hover_color=_icon_hover,
                            text_color=t["gold"], border_color=t["gold"],
                            corner_radius=cr)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("btn_danger_icon", []):
            try:
                w.configure(fg_color=t["card_bg"], hover_color=_icon_hover,
                            text_color=t["danger"], border_color=t["danger"],
                            corner_radius=cr)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        for w in tw.get("checkbox", []):
            try:
                w.configure(text_color=t["text"], fg_color=t["accent"],
                            hover_color=t["accent_hover"], border_color=t["text_muted"],
                            checkmark_color=t["text"])
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        try:
            self.status_lbl.configure(text_color=t["accent"])
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

        if getattr(self, "_paused_mode", False):
            self._show_paused_toggle()
        else:
            self._show_normal_toggle()

        try:
            jh_results_ui.apply_theme(t)
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

        try:
            import jh_notifications
            jh_notifications.apply_theme(t)
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

    # ── API Help ──────────────────────────────────────────────────────────────

    def show_api_help(self):
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
            help_header, text=tr("help_title"),
            font=("Arial", 14, "bold"), text_color=COLOR_CYAN_NEON
        ).pack(side="left")

        ctk.CTkLabel(
            help_win, text=tr("help_text"),
            font=("Arial", 11), text_color=COLOR_TEXT_LIGHT, justify="left"
        ).pack(padx=25, pady=5)

        def _open_help_link():
            ok, reason = jh_url_utils.safely_open_url("https://aistudio.google.com/")
            if not ok:
                import jh_notifications
                jh_notifications.send_notification(
                    tr("invalid_link_title"), tr("invalid_link_body", reason=reason),
                    root=help_win,
                )

        ctk.CTkButton(
            help_win, text=tr("help_btn"),
            font=("Arial", 11, "bold"), fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER, text_color=COLOR_BG_DARK, height=36,
            command=_open_help_link
        ).pack(pady=(15, 5))

        def _show():
            if not help_win.winfo_exists():
                return
            try:
                help_win.attributes("-alpha", 0.0)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            try:
                help_win.update_idletasks()
                w, h = 460, 260
                try:
                    sc = help_win._get_window_scaling()
                except Exception:
                    sc = 1.0
                cpw, cph = w * sc, h * sc
                px = self.winfo_rootx();  py = self.winfo_rooty()
                pw = self.winfo_width();  ph = self.winfo_height()
                x = int(px + (pw - cpw) / 2)
                y = int(py + (ph - cph) / 2)
                help_win.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")
            except Exception:
                help_win.geometry("460x260")
            help_win.deiconify()
            help_win.grab_set()
            help_win.focus_force()
            def _fin():
                if not help_win.winfo_exists():
                    return
                try:
                    _apply_icon_win32(help_win)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                try:
                    help_win.attributes("-alpha", 1.0)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                help_win.after(350, lambda: _apply_icon_win32(help_win) if help_win.winfo_exists() else None)
            help_win.after(100, _fin)
        help_win.after(120, _show)

    # ── Local / cloud provider status ─────────────────────────────────────────

    def set_cloud_provider_status(self, provider):
        api_key = self.app_config.get("api_keys", {}).get(provider, "").strip()
        if not api_key:
            self.update_status(tr("status_key_required", provider=provider), COLOR_GOLD)
        else:
            self.update_status(tr("status_loaded"), COLOR_CYAN_NEON)

    def update_local_server_status(self, provider, _silent=False):
        """Probes the local AI server and reschedules itself every 10 s."""
        servers  = self.app_config.get("local_servers", {}) or {}
        defaults = {"Ollama": "http://localhost:11434", "LM Studio": "http://localhost:1234"}
        base_url = servers.get(provider, defaults.get(provider))

        if not _silent:
            self.update_status(tr("status_local_check", provider=provider), COLOR_GOLD)

        def _probe():
            try:
                is_up, msg = jh_ai_engine.check_local_server(provider, base_url)
            except Exception as e:
                logger.warning(f"[LocalStatus]: {e}")
                is_up, msg = False, "Server unreachable"

            def _apply():
                if not self.winfo_exists():
                    return
                prev_ok = self._local_server_ok
                self._local_server_ok = is_up
                color  = COLOR_CYAN_NEON if is_up else COLOR_GOLD
                prefix = "● " if is_up else "⚠ "
                if not self.is_active:
                    self.update_status(prefix + msg, color)
                elif not is_up and prev_ok:
                    self.update_status(tr("status_server_down", provider=provider), COLOR_RED)

                if self.app_config.get("current_provider") == provider and provider in LOCAL_PROVIDERS:
                    if self._server_poll_after_id is not None:
                        try:
                            self.after_cancel(self._server_poll_after_id)
                        except Exception:
                            logger.debug("Suppressed exception", exc_info=True)
                    self._server_poll_after_id = self.after(
                        10000, lambda: self.update_local_server_status(provider, _silent=True)
                    )
            try:
                self.after(0, _apply)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        threading.Thread(target=_probe, daemon=True).start()

    def maybe_show_local_llm_warning(self, parent_win):
        if not jh_storage_manager.should_show_local_warning(self.app_config):
            return

        warn = ctk.CTkToplevel(parent_win)
        warn.withdraw()
        warn.title(tr("warn_win_title"))
        warn.configure(fg_color=COLOR_BG_DARK)
        force_dark_title_bar(warn)
        warn.transient(parent_win)

        ctk.CTkLabel(warn, text=tr("warn_title"), font=("Arial", 16, "bold"),
                     text_color=COLOR_GOLD).pack(pady=(20, 10), padx=20)
        ctk.CTkLabel(warn, text=tr("warn_text", min_tps=jh_ai_engine.MIN_TOKENS_PER_SEC),
                     font=("Arial", 11), text_color=COLOR_TEXT_LIGHT,
                     justify="left").pack(padx=25, pady=5)

        dont_show_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            warn, text=tr("warn_dont_show"), variable=dont_show_var,
            text_color=COLOR_TEXT_MUTED, fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER, border_color=COLOR_TEXT_MUTED,
            checkbox_width=20, checkbox_height=20, border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        ).pack(pady=(10, 5))

        def close_warning():
            if dont_show_var.get():
                self.app_config["show_local_llm_warning"] = False
                self._set_show_local_warning_async(False)
            try:
                warn.grab_release()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            warn.destroy()
            try:
                parent_win.focus_force()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

        ctk.CTkButton(
            warn, text=tr("warn_ok"), font=("Arial", 12, "bold"),
            fg_color=COLOR_CYAN_NEON, hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK, height=38, command=close_warning
        ).pack(pady=(10, 15))
        warn.protocol("WM_DELETE_WINDOW", close_warning)

        def _show_warn():
            if not warn.winfo_exists():
                return
            try:
                warn.attributes("-alpha", 0.0)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            try:
                warn.update_idletasks()
                w, h = 500, 400
                try:
                    sc = warn._get_window_scaling()
                except Exception:
                    sc = 1.0
                cpw, cph = w * sc, h * sc
                if parent_win and parent_win.winfo_exists():
                    px = parent_win.winfo_rootx(); py = parent_win.winfo_rooty()
                    pw = parent_win.winfo_width(); ph = parent_win.winfo_height()
                    x  = int(px + (pw - cpw) / 2)
                    y  = int(py + (ph - cph) / 2)
                else:
                    x = int((warn.winfo_screenwidth()  - cpw) / 2)
                    y = int((warn.winfo_screenheight() - cph) / 2)
                warn.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")
            except Exception:
                warn.geometry("500x400")
            warn.deiconify(); warn.grab_set(); warn.focus_force()
            def _fin():
                if not warn.winfo_exists():
                    return
                try:
                    _apply_icon_win32(warn)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                try:
                    warn.attributes("-alpha", 1.0)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                warn.after(350, lambda: _apply_icon_win32(warn) if warn.winfo_exists() else None)
            warn.after(100, _fin)
        warn.after(120, _show_warn)

    # ── AI Settings window ────────────────────────────────────────────────────

    def open_ai_settings_window(self):
        settings_win = ctk.CTkToplevel(self)
        settings_win.withdraw()
        settings_win.title("AI Settings")
        settings_win.configure(fg_color=COLOR_BG_DARK)
        force_dark_title_bar(settings_win)

        _t  = THEMES.get(self._active_theme, THEMES["Cyber-Owl"])
        _ff = _t["fonts"]["section"][0]   # "Arial" or "Courier New"
        _f_title    = (_ff, 16, "bold")
        _f_label    = (_ff, 12, "bold")
        _f_seg      = (_ff, 11, "bold")
        _f_preview  = (_ff, 14, "bold")
        _f_save     = (_ff, 13, "bold")
        _seg_hover  = _t.get("secondary_hover", COLOR_INPUT_BG)  # lighter than card for hover

        # ── Title row ──────────────────────────────────────────────────────────
        title_frame = ctk.CTkFrame(settings_win, fg_color="transparent")
        title_frame.pack(pady=(10, 4), padx=30, fill="x")
        title_frame.columnconfigure(0, weight=1)
        title_frame.columnconfigure(1, weight=0)
        title_frame.columnconfigure(2, weight=0)

        ctk.CTkLabel(
            title_frame, text=tr("settings_title"),
            font=_f_title, text_color=COLOR_CYAN_NEON
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            title_frame, text=tr("settings_help"),
            font=_f_seg, text_color=COLOR_CYAN_NEON,
            fg_color="transparent", hover_color=COLOR_INPUT_BG,
            width=75, height=25, command=self.show_api_help
        ).grid(row=0, column=1, sticky="e", padx=(0, 6))

        lang_seg = ctk.CTkSegmentedButton(
            title_frame, values=["EN", "RU"],
            font=_f_seg,
            selected_color=COLOR_CYAN_NEON, selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG, unselected_hover_color=_seg_hover,
            text_color=COLOR_TEXT_LIGHT, width=70, height=25,
        )
        lang_seg.set(jh_i18n.get_language().upper())
        lang_seg.grid(row=0, column=2, sticky="e")

        ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, height=1).pack(
            fill="x", padx=24, pady=(0, 4)
        )

        # ── Two-column scrollable body ─────────────────────────────────────────
        _scroll = ctk.CTkScrollableFrame(
            settings_win, fg_color=COLOR_BG_DARK,
            scrollbar_button_color=COLOR_INPUT_BG,
            scrollbar_button_hover_color=COLOR_CARD_BG,
        )
        _scroll.pack(fill="both", expand=True)
        _scroll.columnconfigure(0, weight=1)
        _scroll.columnconfigure(1, weight=1)
        _scroll.rowconfigure(0, weight=1)
        _scroll.rowconfigure(1, weight=0)

        _left = ctk.CTkFrame(_scroll, fg_color="transparent")
        _left.grid(row=0, column=0, sticky="nsew", padx=(20, 6), pady=(4, 0))

        _right = ctk.CTkFrame(_scroll, fg_color="transparent")
        _right.grid(row=0, column=1, sticky="nsew", padx=(6, 20), pady=(4, 0))

        model_checkboxes   = []
        model_group_frame  = ctk.CTkFrame(_left, fg_color=COLOR_CARD_BG, corner_radius=8)
        temp_api_keys      = self.app_config.get("api_keys", {}).copy()
        current_prov_var   = ctk.StringVar(value=self.app_config.get("current_provider", "Gemini"))
        _slider_ref        = [None]
        _delay_lbl_var     = ctk.StringVar()
        _initialized       = [False]

        def _update_delay_label(val):
            _delay_lbl_var.set(tr("delay_label", val=int(float(val))))

        def _apply_slider_state(_provider):
            slider = _slider_ref[0]
            if slider is not None:
                slider.configure(state="normal")
                _update_delay_label(slider.get())

        def _reapply_show_mask():
            try:
                api_key_entry.configure(show="*")
            except Exception:
                try:
                    api_key_entry._entry.configure(show="*")
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)

        def apply_local_key_field_state(provider):
            is_local = provider in LOCAL_PROVIDERS
            if is_local:
                temp_api_keys[provider] = "local"
                try:
                    api_key_entry.configure(state="normal")
                    api_key_entry.delete(0, "end")
                    api_key_entry.configure(state="disabled",
                                            placeholder_text=tr("key_placeholder_local"))
                    _reapply_show_mask()
                except Exception as e:
                    logger.warning(f"[Settings]: {e}")
            else:
                try:
                    api_key_entry.configure(state="normal",
                                            placeholder_text=tr("key_placeholder"))
                    saved_key = temp_api_keys.get(provider, "")
                    api_key_entry.delete(0, "end")
                    if saved_key:
                        api_key_entry.insert(0, saved_key)
                    _reapply_show_mask()
                except Exception as e:
                    logger.warning(f"[Settings]: {e}")

        def on_provider_changed(new_provider):
            if _initialized[0]:
                old = self.app_config.get("current_provider", "Gemini")
                if old not in LOCAL_PROVIDERS:
                    try:
                        if str(api_key_entry.cget("state")) != "disabled":
                            temp_api_keys[old] = api_key_entry.get().strip()
                    except Exception:
                        logger.debug("Suppressed exception", exc_info=True)

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
                    model_group_frame, text=m_name, variable=cb_var,
                    text_color=COLOR_TEXT_LIGHT, fg_color=COLOR_CYAN_NEON,
                    hover_color=COLOR_CYAN_HOVER, border_color=COLOR_TEXT_MUTED,
                    checkbox_width=20, checkbox_height=20, border_width=2,
                    checkmark_color=COLOR_TEXT_LIGHT,
                    command=lambda n=m_name, v=cb_var: _update_active_models(new_provider, n, v.get())
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

        def _update_active_models(provider, name, is_selected):
            if provider not in self.app_config["active_models"]:
                self.app_config["active_models"][provider] = []
            curr = self.app_config["active_models"][provider]
            if is_selected and name not in curr:
                curr.append(name)
            elif not is_selected and name in curr:
                curr.remove(name)

        # ── Left column: AI provider ───────────────────────────────────────────
        ctk.CTkLabel(_left, text=tr("provider_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        provider_dropdown = ctk.CTkOptionMenu(
            _left, values=PROVIDER_ORDER, variable=current_prov_var,
            command=on_provider_changed,
            fg_color=COLOR_CARD_BG, button_color=COLOR_INPUT_BG,
            button_hover_color=COLOR_CARD_BG, text_color=COLOR_TEXT_LIGHT,
            dropdown_fg_color=COLOR_CARD_BG, dropdown_hover_color=COLOR_INPUT_BG,
            dropdown_text_color=COLOR_TEXT_LIGHT
        )
        provider_dropdown.pack(pady=(0, 6), fill="x")

        ctk.CTkFrame(_left, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(_left, text=tr("key_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        api_key_entry = ctk.CTkEntry(
            _left, height=40, fg_color=COLOR_INPUT_BG, border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT, placeholder_text=tr("key_placeholder"), show="*"
        )
        api_key_entry.pack(pady=(0, 6), fill="x")
        bind_russian_hotkeys(api_key_entry)

        ctk.CTkFrame(_left, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(_left, text=tr("models_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        model_group_frame.pack(pady=(0, 6), fill="x")

        on_provider_changed(current_prov_var.get())
        _initialized[0] = True

        # ── Right column: behaviour / hotkey ──────────────────────────────────
        ctk.CTkLabel(_right, textvariable=_delay_lbl_var,
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        current_delay = self.app_config.get("request_delay", 15)
        delay_slider = ctk.CTkSlider(
            _right, from_=0, to=60, number_of_steps=60,
            command=_update_delay_label,
            button_color=COLOR_CYAN_NEON, button_hover_color=COLOR_CYAN_HOVER,
            progress_color=COLOR_CYAN_NEON, fg_color=COLOR_INPUT_BG
        )
        delay_slider.pack(pady=(0, 6), fill="x")
        delay_slider.set(current_delay)
        _slider_ref[0] = delay_slider
        _apply_slider_state(current_prov_var.get())

        ctk.CTkFrame(_right, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        # ── Filter strictness ──────────────────────────────────────────────────
        ctk.CTkLabel(_right, text=tr("strictness_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        strictness_labels = [tr("strictness_mild"), tr("strictness_balanced"), tr("strictness_strict")]
        strictness_seg = ctk.CTkSegmentedButton(
            _right, values=strictness_labels, font=_f_seg,
            selected_color=COLOR_CYAN_NEON, selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG, unselected_hover_color=_seg_hover,
            text_color=COLOR_TEXT_LIGHT,
        )
        strictness_seg.pack(pady=(0, 6), fill="x")
        current_strictness = self.app_config.get("filter_strictness", 2)
        strictness_seg.set(strictness_labels[max(0, min(2, current_strictness - 1))])

        ctk.CTkFrame(_right, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        # ── Letter length ──────────────────────────────────────────────────────
        ctk.CTkLabel(_right, text=tr("letter_length_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        letter_labels = [tr("letter_short"), tr("letter_balanced"), tr("letter_detailed")]
        letter_seg = ctk.CTkSegmentedButton(
            _right, values=letter_labels, font=_f_seg,
            selected_color=COLOR_CYAN_NEON, selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG, unselected_hover_color=_seg_hover,
            text_color=COLOR_TEXT_LIGHT,
        )
        letter_seg.pack(pady=(0, 6), fill="x")
        current_letter = self.app_config.get("letter_length", 2)
        letter_seg.set(letter_labels[max(0, min(2, current_letter - 1))])

        ctk.CTkFrame(_right, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        # ── Capture hotkey (visual selector) ──────────────────────────────────
        from jh_automation import HotkeySpec as _HotkeySpec
        _hs = _HotkeySpec.from_config(self.app_config)

        ctk.CTkLabel(_right, text=tr("hotkey_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        _hk_row = ctk.CTkFrame(_right, fg_color="transparent")
        _hk_row.pack(pady=(0, 4), fill="x")
        _hk_row.columnconfigure(0, weight=1)
        _hk_row.columnconfigure(1, weight=1)
        _hk_row.columnconfigure(2, weight=1)

        _dd_kw = dict(
            fg_color=COLOR_CARD_BG, button_color=COLOR_INPUT_BG,
            button_hover_color=COLOR_CARD_BG, text_color=COLOR_TEXT_LIGHT,
            dropdown_fg_color=COLOR_CARD_BG, dropdown_hover_color=COLOR_INPUT_BG,
            dropdown_text_color=COLOR_TEXT_LIGHT,
        )

        _mod1_var = ctk.StringVar(value=_hs.mod1.capitalize())
        _mod2_var = ctk.StringVar(
            value="None" if _hs.mod2 == "none" else _hs.mod2.capitalize()
        )
        _key_var  = ctk.StringVar(value=_hs.key.upper())

        _hk_preview_var = ctk.StringVar()

        def _refresh_hk_preview(*_):
            m1 = _mod1_var.get()
            m2 = _mod2_var.get()
            k  = _key_var.get()
            parts = [m1] + ([m2] if m2 != "None" else []) + [k]
            _hk_preview_var.set("  " + "  +  ".join(parts) + "  ")

        ctk.CTkOptionMenu(
            _hk_row, values=["Ctrl", "Alt", "Win"],
            variable=_mod1_var, command=_refresh_hk_preview, **_dd_kw,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 2))

        ctk.CTkOptionMenu(
            _hk_row, values=["Shift", "None"],
            variable=_mod2_var, command=_refresh_hk_preview, **_dd_kw,
        ).grid(row=0, column=1, sticky="ew", padx=2)

        ctk.CTkOptionMenu(
            _hk_row, values=list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            variable=_key_var, command=_refresh_hk_preview, **_dd_kw,
        ).grid(row=0, column=2, sticky="ew", padx=(2, 0))

        _refresh_hk_preview()

        ctk.CTkLabel(
            _right, textvariable=_hk_preview_var,
            font=_f_preview, text_color=COLOR_CYAN_NEON,
            fg_color=COLOR_CARD_BG, corner_radius=6, height=38,
        ).pack(pady=(0, 6), fill="x")

        ctk.CTkFrame(_right, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        # ── Notifications ──────────────────────────────────────────────────────
        notif_var = ctk.BooleanVar(value=bool(self.app_config.get("notifications_enabled", True)))
        ctk.CTkCheckBox(
            _right, text=tr("cb_notifications"), variable=notif_var,
            text_color=COLOR_TEXT_LIGHT, fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER, border_color=COLOR_TEXT_MUTED,
            checkbox_width=20, checkbox_height=20, border_width=2,
            checkmark_color=COLOR_TEXT_LIGHT
        ).pack(anchor="w", pady=(0, 8))

        # ── Theme ──────────────────────────────────────────────────────────────
        ctk.CTkFrame(_right, fg_color=COLOR_CARD_BG, height=1).pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(_right, text=tr("theme_label"),
                     font=_f_label, text_color=COLOR_TEXT_LIGHT
                     ).pack(anchor="w", pady=(0, 3))

        def _apply_theme_and_reopen(name):
            self.apply_theme(name)
            settings_win.destroy()
            self.after(60, self.open_ai_settings_window)

        theme_seg = ctk.CTkSegmentedButton(
            _right, values=list(THEMES.keys()),
            font=_f_seg,
            selected_color=COLOR_CYAN_NEON, selected_hover_color=COLOR_CYAN_HOVER,
            unselected_color=COLOR_CARD_BG, unselected_hover_color=_seg_hover,
            text_color=COLOR_TEXT_LIGHT,
            command=_apply_theme_and_reopen,
        )
        theme_seg.set(self._active_theme)
        theme_seg.pack(pady=(0, 8), fill="x")

        # ── Collect & save ─────────────────────────────────────────────────────
        def _collect_state():
            active_prov = current_prov_var.get()
            if active_prov in LOCAL_PROVIDERS:
                temp_api_keys[active_prov] = "local"
            else:
                try:
                    if str(api_key_entry.cget("state")) != "disabled":
                        temp_api_keys[active_prov] = api_key_entry.get().strip()
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
            self.app_config["current_provider"]   = active_prov
            self.app_config["api_keys"]            = temp_api_keys
            self.app_config["request_delay"]       = int(delay_slider.get())
            try:
                s_idx = strictness_labels.index(strictness_seg.get())
            except ValueError:
                s_idx = 1
            self.app_config["filter_strictness"] = s_idx + 1
            try:
                l_idx = letter_labels.index(letter_seg.get())
            except ValueError:
                l_idx = 1
            self.app_config["letter_length"]      = l_idx + 1
            self.app_config["notifications_enabled"] = bool(notif_var.get())
            self.app_config["hotkey"] = {
                "mod1": _mod1_var.get().lower(),
                "mod2": _mod2_var.get().lower(),
                "key":  _key_var.get().upper(),
            }

        def save_and_close():
            # Guard: refuse to register a bare-letter hotkey (no modifiers).
            # On Windows, RegisterHotKey with fsModifiers=0 would globally
            # hijack the physical key, making it untypeable anywhere in the OS
            # until the process is killed.  required_mods() is empty when both
            # dropdowns resolve to "none", catching any such configuration.
            from jh_automation import HotkeySpec as _HotkeySpec
            _preview = _HotkeySpec(
                mod1=_mod1_var.get().lower(),
                mod2=_mod2_var.get().lower(),
                key=_key_var.get().upper(),
            )
            if not _preview.required_mods():
                messagebox.showerror(
                    "Invalid Hotkey",
                    "At least one modifier key (Ctrl, Alt, Shift, or Win) is required.\n\n"
                    "Registering a bare letter as a global hotkey would make that key "
                    "untypeable anywhere in the operating system.",
                    parent=settings_win,
                )
                return
            _collect_state()
            jh_storage_manager.save_config(self.app_config)
            # Re-register hotkey immediately — no app restart required.
            automation = getattr(self, "_automation", None)
            if automation is not None:
                try:
                    from jh_automation import HotkeySpec
                    automation.set_hotkey(HotkeySpec.from_config(self.app_config))
                except Exception as _hk_exc:
                    logger.error(f"[Settings]: Hotkey re-registration failed: {_hk_exc}")
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
            self.after(80, self.open_ai_settings_window)

        lang_seg.configure(command=on_language_changed)

        # ── Fixed footer: Save button always visible outside the scroll area ──
        ctk.CTkFrame(settings_win, fg_color=COLOR_CARD_BG, height=1).pack(
            fill="x", padx=24, pady=(4, 0)
        )
        ctk.CTkButton(
            settings_win, text=tr("btn_save"),
            font=_f_save, fg_color=COLOR_CYAN_NEON,
            hover_color=COLOR_CYAN_HOVER, text_color=COLOR_BG_DARK,
            height=40, command=save_and_close
        ).pack(fill="x", padx=20, pady=(10, 14))

        # ── Show window ────────────────────────────────────────────────────────
        def _show_window():
            if not settings_win.winfo_exists():
                return
            try:
                settings_win.attributes("-alpha", 0.0)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            try:
                settings_win.update_idletasks()
                w, h = 700, 520   # two-column layout; scroll absorbs DPI overflow
                try:
                    sc = settings_win._get_window_scaling()
                except Exception:
                    sc = 1.0
                cpw, cph = w * sc, h * sc
                if self.winfo_exists():
                    px = self.winfo_rootx(); py = self.winfo_rooty()
                    pw = self.winfo_width(); ph = self.winfo_height()
                    x  = int(px + (pw - cpw) / 2)
                    y  = int(py + (ph - cph) / 2)
                else:
                    x = int((settings_win.winfo_screenwidth()  - cpw) / 2)
                    y = int((settings_win.winfo_screenheight() - cph) / 2)
                settings_win.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")
            except Exception:
                settings_win.geometry("700x520")
            settings_win.deiconify()
            settings_win.grab_set()
            settings_win.focus_force()
            def _finalize():
                if not settings_win.winfo_exists():
                    return
                try:
                    _apply_icon_win32(settings_win)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                try:
                    settings_win.attributes("-alpha", 1.0)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                settings_win.after(350, lambda: _apply_icon_win32(settings_win) if settings_win.winfo_exists() else None)
            settings_win.after(100, _finalize)

        settings_win.after(120, _show_window)

    # ── Config I/O ────────────────────────────────────────────────────────────

    def load_config_to_ui(self):
        self.first_name_input.delete(0, "end")
        self.first_name_input.insert(0, self.app_config.get("first_name", ""))
        self.last_name_input.delete(0, "end")
        self.last_name_input.insert(0, self.app_config.get("last_name", ""))
        self.resume_input.delete("0.0", "end")
        self.resume_input.insert("0.0", self.app_config.get("resume", ""))

        if not self.app_config.get("filter_remote", True):   self.cb_remote.deselect()
        if self.app_config.get("filter_office", False):       self.cb_office.select()
        if self.app_config.get("filter_hybrid", False):       self.cb_hybrid.select()
        if not self.app_config.get("filter_location", True):  self.cb_location.deselect()
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
        self.app_config["first_name"]       = self.first_name_input.get().strip()
        self.app_config["last_name"]        = self.last_name_input.get().strip()
        self.app_config["resume"]           = self.resume_input.get("0.0", "end-1c").strip()
        self.app_config["filter_remote"]    = bool(self.cb_remote.get())
        self.app_config["filter_office"]    = bool(self.cb_office.get())
        self.app_config["filter_hybrid"]    = bool(self.cb_hybrid.get())
        self.app_config["filter_location"]  = bool(self.cb_location.get())
        self.app_config["user_location"]    = self.location_entry.get().strip()
        jh_storage_manager.save_config(self.app_config)

    def set_inputs_state(self, state):
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
        def _bg():
            try:
                jh_storage_manager.set_show_local_warning(value)
            except Exception as e:
                logger.warning(f"[Config]: {e}")
        threading.Thread(target=_bg, daemon=True).start()

    # ── Toggle (Start / Stop) ─────────────────────────────────────────────────

    def toggle_assistant(self):
        """Starts or stops the AI processing queue."""
        if not self.is_active:
            provider   = self.app_config.get("current_provider", "Gemini")
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
                messagebox.showerror(tr("err_start_title"), tr("err_name_msg"), parent=self)
                return

            was_paused = self._paused_mode
            self._paused_mode = False
            if not was_paused:
                self._session_processed = 0
                self._session_approved  = 0
                self._session_rejected  = 0

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

            self.is_active = True
            self.btn_toggle.configure(
                text=tr("btn_stop"), fg_color=COLOR_RED,
                hover_color=COLOR_RED_HOVER, text_color=COLOR_TEXT_LIGHT, state="normal"
            )
            try:
                from jh_automation import HotkeySpec
                _hk_display = HotkeySpec.from_config(self.app_config).display()
            except Exception:
                _hk_display = "Ctrl + Shift + X"
            self.status_lbl.configure(
                text=tr("status_active", hotkey=_hk_display), text_color=COLOR_CYAN_NEON
            )

        else:
            self.is_active = False
            self.stop_worker_event.set()
            self.set_inputs_state("normal")
            self._show_normal_toggle()
            self.status_lbl.configure(text=tr("status_stopped"), text_color=COLOR_RED)

            q_size = self.vacancy_queue.qsize() + (1 if self._worker_has_item else 0)
            if q_size > 0:
                self._show_paused_toggle(q_size)
                self.status_lbl.configure(text=tr("status_paused", q=q_size), text_color=COLOR_GOLD)

    # ── Thread safety helpers ─────────────────────────────────────────────────

    def update_status(self, text, color):
        """
        Thread-safe status label update.

        Uses self._alive rather than winfo_exists() as the guard: winfo_exists()
        is a Tkinter call that must only run on the main thread, but update_status
        is called from background worker threads.  self.after() is the one Tkinter
        method explicitly documented as safe to call from any thread; _alive gates
        the call so we don't schedule callbacks into a destroyed root window.
        """
        if self._alive.is_set():
            try:
                self.after(0, lambda: self.status_lbl.configure(text=text, text_color=color))
            except Exception as e:
                logger.warning(f"[Status]: {e}")

    def _safe_after(self, ms, callback):
        if self._alive.is_set():
            try:
                self.after(ms, callback)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)

    # ── Vacancy queue ─────────────────────────────────────────────────────────

    def enqueue_vacancy(self, data):
        """
        Single entry point for payloads produced by BrowserCaptureEngine.

        Performs O(1) dedup via the in-memory URL sets BEFORE the item enters
        the queue — so a duplicate is dropped immediately instead of sitting
        through the full request-delay countdown only to be discarded by the
        worker. Also advances _batch_id so the worker's "queue done"
        notification guard can detect that new work arrived.

        Called from the automation daemon thread — queue.Queue.put(),
        update_status() (via .after), and the storage checks (lock-guarded)
        are all safe to invoke from there.
        """
        # Failure sentinels must always reach the worker so it can reset the UI
        # loading state; they carry no URL and bypass dedup/counters entirely.
        if data.get("status") == "failed":
            self.vacancy_queue.put(data)
            return

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
        """Background loop: pulls vacancies from queue and processes them."""
        while not self.stop_worker_event.is_set():
            try:
                vacancy_data = self.vacancy_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._worker_has_item = True

                # Failure sentinel pushed by BrowserCaptureEngine when the capture
                # pipeline aborts after notify_fn() fires.  Reset the UI immediately
                # without going through the delay countdown, then discard the item.
                if vacancy_data.get("status") == "failed":
                    error = vacancy_data.get("error", "capture_error")
                    self._safe_after(
                        0,
                        lambda e=error: self.update_status(
                            tr("status_proc_error", msg=e), COLOR_RED
                        ),
                    )
                    try:
                        self.vacancy_queue.task_done()
                    except Exception:
                        logger.debug("Suppressed exception", exc_info=True)
                    continue

                delay_seconds = self.app_config.get("request_delay", 15)

                if delay_seconds == 0:
                    current_q = self.vacancy_queue.qsize() + 1
                    self.update_status(
                        tr("status_queue", sec=0, q=current_q, done=self._session_processed),
                        COLOR_GOLD
                    )
                    if self.stop_worker_event.is_set():
                        self.vacancy_queue.put(vacancy_data)
                        return
                else:
                    for remaining in range(delay_seconds, 0, -1):
                        current_q = self.vacancy_queue.qsize() + 1
                        self.update_status(
                            tr("status_queue", sec=remaining, q=current_q, done=self._session_processed),
                            COLOR_GOLD
                        )
                        for _ in range(5):
                            if self.stop_worker_event.is_set():
                                self.vacancy_queue.put(vacancy_data)
                                return
                            time.sleep(0.2)

                if not self.stop_worker_event.is_set():
                    url = vacancy_data.get("url", "")
                    if url and url != "#" and (
                        jh_storage_manager.vacancy_url_in_approved(url) or
                        jh_storage_manager.vacancy_url_in_rejected(url)
                    ):
                        self.update_status(tr("status_duplicate_db"), COLOR_TEXT_MUTED)
                        try:
                            self.vacancy_queue.task_done()
                        except Exception:
                            logger.debug("Suppressed exception", exc_info=True)
                        continue

                    self.process_incoming_vacancy(vacancy_data)
                    try:
                        self.vacancy_queue.task_done()
                    except Exception:
                        logger.debug("Suppressed exception", exc_info=True)

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
                                        root=self,
                                        on_click=self._bring_to_front,
                                        is_error=False,
                                    )
                                except Exception:
                                    logger.debug("Suppressed exception", exc_info=True)
                        self._safe_after(2000, _deferred_notif)

            except Exception as exc:
                import traceback
                logger.error(f"[Worker]: Unhandled error processing vacancy: {exc}")
                traceback.print_exc()
                try:
                    self.vacancy_queue.task_done()
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)

            finally:
                self._worker_has_item = False

    def process_incoming_vacancy(self, vacancy_data):
        """Sends one vacancy through the AI engine and persists the result."""
        self.update_status(tr("status_analyzing"), COLOR_GOLD)
        # self.app_config is kept current in-memory by the settings window
        # (save_and_close / on_language_changed mutate it in place), so there is
        # no need to re-read and re-parse config.json from disk on every single
        # vacancy. Just make sure the engine renders reject reasons in the
        # currently-selected language.
        jh_i18n.set_language(self.app_config.get("language", "en"))

        try:
            status, result_text, extracted_info = jh_ai_engine.analyze_and_generate(
                vacancy_data, self.app_config,
                cancel_event=self.stop_worker_event,
            )
            company         = extracted_info.get("company", vacancy_data.get("company", "Unknown"))
            title           = extracted_info.get("title",   vacancy_data.get("title",   "Unknown"))
            url             = vacancy_data.get("url", "#")
            description     = vacancy_data.get("text", "")
            vacancy_country = extracted_info.get("vacancy_country", "")

            if status == "APPROVED":
                jh_storage_manager.save_approved_vacancy(
                    company=company, title=title, url=url,
                    cover_letter=result_text, description=description,
                    vacancy_country=vacancy_country,
                )
                self._session_approved  += 1
                self._session_processed += 1
                self.update_status(tr("status_approved", title=title, company=company), COLOR_CYAN_NEON)
            elif status == "REJECTED":
                jh_storage_manager.save_rejected_vacancy(
                    company=company, title=title, url=url, reason=result_text,
                    vacancy_country=vacancy_country,
                )
                self._session_rejected  += 1
                self._session_processed += 1
                self.update_status(tr("status_rejected", title=title, company=company), COLOR_RED)
            elif result_text == "cancelled":
                # Vacancy was cancelled between Stage 1 and Stage 2 by stop_worker_event.
                # Re-queue it so it is processed when the user resumes, then return
                # without incrementing processed counters or showing an error.
                self.vacancy_queue.put(vacancy_data)
                return
            else:
                self.update_status(tr("status_error", msg=result_text), COLOR_RED)
        except Exception as e:
            self.update_status(tr("status_proc_error", msg=str(e)), COLOR_RED)
            if self.app_config.get("notifications_enabled", True):
                try:
                    import jh_notifications
                    jh_notifications.send_notification("Job Hunter AI", tr("notif_error_body"), root=self, on_click=self._bring_to_front, is_error=True)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)

    # ── PDF import ────────────────────────────────────────────────────────────

    def import_resume_from_pdf(self):
        filepath = filedialog.askopenfilename(
            parent=self, title=tr("btn_pdf_import"),
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
                # Extract once per page — extract_text() is the expensive call,
                # so never invoke it twice (once in the filter, once in the body).
                pages_text = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                raw_text   = "\n".join(pages_text).strip()
                if not raw_text:
                    self.after(0, lambda: self.update_status(tr("pdf_error_no_text"), COLOR_RED))
                    self.after(0, lambda: self.btn_pdf_import.configure(state="normal"))
                    return
                config   = jh_storage_manager.load_config()
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

    # ── Resume history ────────────────────────────────────────────────────────

    def open_resume_history(self):
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
                ctk.CTkLabel(scroll_frame, text=tr("history_empty"),
                             font=("Arial", 12), text_color=COLOR_TEXT_MUTED).pack(pady=20)
                return
            for item in history:
                name = item.get("name", ""); text = item.get("text", "")
                row  = ctk.CTkFrame(scroll_frame, fg_color=COLOR_CARD_BG, corner_radius=6)
                row.pack(fill="x", padx=8, pady=3)
                ctk.CTkLabel(row, text=name, font=("Arial", 12, "bold"),
                             text_color=COLOR_TEXT_LIGHT, anchor="w"
                             ).pack(side="left", padx=12, pady=8, fill="x", expand=True)

                def _load(t=text):
                    self.resume_input.delete("0.0", "end")
                    self.resume_input.insert("0.0", t)
                    hist_win.destroy()

                ctk.CTkButton(row, text=tr("history_btn_load"), width=65, height=28,
                              font=("Arial", 11, "bold"), fg_color=COLOR_CYAN_NEON,
                              hover_color=COLOR_CYAN_HOVER, text_color=COLOR_BG_DARK,
                              command=_load).pack(side="right", padx=(4, 4), pady=6)

                def _delete(n=name, sf=scroll_frame):
                    jh_storage_manager.delete_resume_from_history(n)
                    _refresh(sf)

                ctk.CTkButton(row, text=tr("history_btn_delete"), width=30, height=28,
                              font=("Arial", 11, "bold"), fg_color=COLOR_RED,
                              hover_color=COLOR_RED_HOVER, text_color=COLOR_TEXT_LIGHT,
                              command=_delete).pack(side="right", padx=(0, 4), pady=6)

        hist_header = ctk.CTkFrame(hist_win, fg_color="transparent")
        hist_header.pack(pady=(15, 8), padx=20)
        hist_logo = self.load_and_resize_logo(22)
        if hist_logo:
            ctk.CTkLabel(hist_header, image=hist_logo, text="").pack(side="left", padx=(0, 8))
        ctk.CTkLabel(hist_header, text=tr("history_win_title"),
                     font=("Arial", 14, "bold"), text_color=COLOR_CYAN_NEON).pack(side="left")

        scroll = ctk.CTkScrollableFrame(hist_win, fg_color=COLOR_BG_DARK, height=240)
        scroll.pack(fill="x", padx=12, pady=(0, 8))
        _refresh(scroll)

        ctk.CTkFrame(hist_win, height=1, fg_color=COLOR_CARD_BG).pack(fill="x", padx=12, pady=4)

        save_frame = ctk.CTkFrame(hist_win, fg_color="transparent")
        save_frame.pack(fill="x", padx=12, pady=(4, 15))

        name_entry = ctk.CTkEntry(
            save_frame, placeholder_text=tr("history_save_name_ph"),
            height=34, fg_color=COLOR_INPUT_BG, border_color=COLOR_CARD_BG,
            text_color=COLOR_TEXT_LIGHT, placeholder_text_color=COLOR_TEXT_MUTED,
            font=("Arial", 11)
        )
        name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def _save_current():
            name = name_entry.get().strip()
            if not name:
                self.update_status(tr("history_name_empty"), COLOR_GOLD)
                return
            current_text = self.resume_input.get("0.0", "end-1c").strip()
            existing = [r.get("name") for r in jh_storage_manager.get_resume_history()]
            if name in existing:
                ok = messagebox.askyesno(
                    tr("history_win_title"), tr("history_overwrite_q", name=name), parent=hist_win
                )
                if not ok:
                    return
            jh_storage_manager.save_resume_to_history(name, current_text)
            _refresh(scroll)
            name_entry.delete(0, "end")

        ctk.CTkButton(save_frame, text=tr("history_btn_save"), height=34,
                      font=("Arial", 11, "bold"), fg_color=COLOR_GOLD,
                      hover_color=COLOR_GOLD_HOVER, text_color=COLOR_BG_DARK,
                      command=_save_current).pack(side="right")

        def _show_hist():
            if not hist_win.winfo_exists():
                return
            try:
                hist_win.attributes("-alpha", 0.0)
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            try:
                hist_win.update_idletasks()
                w, h = 460, 420
                try:
                    sc = hist_win._get_window_scaling()
                except Exception:
                    sc = 1.0
                cpw, cph = w * sc, h * sc
                px = self.winfo_rootx(); py = self.winfo_rooty()
                pw = self.winfo_width(); ph = self.winfo_height()
                x = int(px + (pw - cpw) / 2)
                y = int(py + (ph - cph) / 2)
                hist_win.geometry(f"{w}x{h}+{max(0,x)}+{max(0,y)}")
            except Exception:
                hist_win.geometry("460x420")
            hist_win.deiconify(); hist_win.grab_set(); hist_win.focus_force()
            def _fin():
                if not hist_win.winfo_exists():
                    return
                try:
                    _apply_icon_win32(hist_win)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                try:
                    hist_win.attributes("-alpha", 1.0)
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)
                hist_win.after(350, lambda: _apply_icon_win32(hist_win) if hist_win.winfo_exists() else None)
            hist_win.after(100, _fin)
        hist_win.after(120, _show_hist)

    def open_results(self):
        jh_results_ui.apply_theme(THEMES.get(self._active_theme, THEMES["Cyber-Owl"]))
        jh_results_ui.open_window(self)


# =====================================================================
# SINGLE-INSTANCE GUARD  +  WAKE-UP SIGNALLING
# =====================================================================

_WAKE_PORT = 57321  # loopback port used to signal the running instance


def _signal_running_instance() -> None:
    """Connect to the running instance's wake listener and ask it to restore."""
    import socket as _socket
    try:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", _WAKE_PORT))
            s.sendall(b"wake")
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)


def _acquire_single_instance_lock():
    """
    Ensures only one instance of Job Hunter AI runs per user session.

    Windows — Named mutex with "Local\\" prefix.  CreateMutexW returns a
    handle even when the mutex already exists; GetLastError() == 183
    (ERROR_ALREADY_EXISTS) indicates a duplicate.  Before exiting, the
    second instance sends a wake signal over _WAKE_PORT so the running
    instance restores itself from the tray.

    Linux / macOS — Bind a loopback TCP socket on _WAKE_PORT.  OSError
    on bind() means the port is already held by a running instance; we
    connect to it and send the wake signal before exiting.

    Must be called before any Tkinter or tray initialisation.
    """
    if sys.platform == "win32":
        import ctypes
        ERROR_ALREADY_EXISTS = 183
        handle = ctypes.windll.kernel32.CreateMutexW(
            None, False, "Local\\JobHunterAI_v3_SingleInstance"
        )
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            logger.warning("[SingleInstance]: Another instance is already running. Signalling it.")
            _signal_running_instance()
            os._exit(0)
        return handle  # Keep alive — OS closes it when the process exits
    else:
        import socket as _socket
        _sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        _sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 0)
        try:
            _sock.bind(("127.0.0.1", _WAKE_PORT))
        except OSError:
            logger.warning("[SingleInstance]: Another instance is already running. Signalling it.")
            _signal_running_instance()
            os._exit(0)
        return _sock  # Keep reference alive; never .close()'d


def _start_wake_listener(lock_obj, callback) -> None:
    """
    Starts a background thread that listens for wake signals from future
    instances.  When a signal arrives, *callback* is invoked (on the
    caller's thread — use app.after() to marshal onto the Tk thread).

    On Windows lock_obj is a mutex handle, so we open a fresh server
    socket on _WAKE_PORT.  On Linux/macOS lock_obj is the already-bound
    socket; we just call listen() on it.
    """
    import socket as _socket

    if sys.platform == "win32":
        srv = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        srv.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", _WAKE_PORT))
            srv.listen(1)
        except OSError:
            srv.close()
            return
    else:
        srv = lock_obj
        try:
            srv.listen(1)
        except Exception:
            return

    def _loop():
        while True:
            try:
                conn, _ = srv.accept()
                conn.close()
                callback()
            except Exception:
                break

    t = threading.Thread(target=_loop, daemon=True, name="WakeListener")
    t.start()


# =====================================================================
# СТАРТ ПРИЛОЖЕНИЯ
# =====================================================================
# Module-level declaration ensures Python's GC never collects the lock
# object before the process exits.  A socket stored only as a function-
# local would be closed by __del__ the moment its frame is torn down,
# releasing the bind and allowing a second instance to start.
_SINGLE_INSTANCE_LOCK = None

if __name__ == "__main__":
    _SINGLE_INSTANCE_LOCK = _acquire_single_instance_lock()
    app = JobHunterApp()
    _start_wake_listener(_SINGLE_INSTANCE_LOCK, lambda: app.after(0, app._bring_to_front))
    app.mainloop()
