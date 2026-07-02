# jh_notifications.py — in-app Telegram-style toast (no external dependencies)
import threading
from jh_log import get_logger

logger = get_logger(__name__)

_toast_ref = [None]           # единственный активный тост; новый вытесняет старый
_notification_lock = threading.Lock()  # guards _toast_ref mutations from concurrent threads

# ── Логические размеры (при 100% масштабе / 96 DPI) ─────────────────────────
# Аналогично тому как остальные окна задают w, h в логических пикселях,
# а позицию вычисляют через _get_window_scaling() для физических координат.
_W_LOG      = 380     # ширина тоста
_H_LOG      = 96      # высота тоста
_MARGIN_LOG = 8       # отступ от края экрана
_TASKBAR_LOG = 42     # резерв над панелью задач (≈высота стандартного таскбара)
_LIFT_LOG   = 72      # насколько ниже финальной позиции стартует анимация
_BAR_LOG    = 4       # ширина цветной левой полосы
_PAD_X_LOG  = 14      # горизонтальный padding контента
_PAD_Y_LOG  = 11      # вертикальный padding контента

# ── Цвета ────────────────────────────────────────────────────────────────────
BG          = "#111622"
BORDER      = "#1D2535"
TITLE       = "#E9EDF0"
BODY        = "#B0BAC6"
MUTED       = "#6B778A"
CYAN        = "#00D8C6"
RED         = "#D24B4B"
FONT_FAMILY = "Segoe UI"


def apply_theme(theme_dict: dict) -> None:
    """Sync toast colors and font family from the active theme dict."""
    global BG, BORDER, TITLE, BODY, MUTED, CYAN, RED, FONT_FAMILY
    BG          = theme_dict.get("card_bg",         BG)
    BORDER      = theme_dict.get("secondary_hover", BORDER)
    TITLE       = theme_dict.get("text",            TITLE)
    BODY        = theme_dict.get("text",            BODY)
    MUTED       = theme_dict.get("text_muted",      MUTED)
    CYAN        = theme_dict.get("accent",          CYAN)
    RED         = theme_dict.get("danger",          RED)
    fonts = theme_dict.get("fonts", {})
    if fonts:
        FONT_FAMILY = fonts.get("section", (FONT_FAMILY,))[0]


def _get_scale(root) -> float:
    """
    Возвращает DPI scale-фактор — тот же метод, что использует главное окно.
    Приоритет: CTk-метод → Windows API → 1.0.
    """
    try:
        return root._get_window_scaling()
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return dpi / 96.0
    except Exception:
        return 1.0


def _play_sound(is_error: bool) -> None:
    """Тихий системный звук Windows в фоновом потоке."""
    try:
        import winsound
        # MB_ICONEXCLAMATION(48) — предупреждение, мягкий
        # MB_ICONASTERISK(64)    — информация, стандартный звук уведомления
        winsound.MessageBeep(48 if is_error else 64)
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)


def _build_toast_safe(root, message: str, is_error: bool = False, on_click=None) -> None:
    """Создаёт Telegram-стайл тост в правом нижнем углу экрана (thread-safe)."""
    import tkinter as tk

    # ── Atomically destroy the previous toast before creating a new one ───────
    # _notification_lock guards _toast_ref against concurrent mutations from
    # multiple worker threads queuing toasts at the same time.
    with _notification_lock:
        if _toast_ref[0] is not None:
            try:
                if _toast_ref[0].winfo_exists():
                    _toast_ref[0].destroy()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            finally:
                _toast_ref[0] = None

    # ── DPI scale — единственный источник истины для всех размеров ──────────
    sc = _get_scale(root)

    # Физические размеры: логические × scale (как в _show_with_icon и _show_window)
    W      = int(_W_LOG      * sc)
    H      = int(_H_LOG      * sc)
    MARGIN = int(_MARGIN_LOG * sc)
    TBR    = int(_TASKBAR_LOG * sc)
    LIFT   = int(_LIFT_LOG   * sc)
    BAR    = int(_BAR_LOG    * sc)
    PX     = int(_PAD_X_LOG  * sc)
    PY     = int(_PAD_Y_LOG  * sc)

    # Позиция: физические координаты экрана (winfo_screenwidth тоже физические)
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    final_x = sw - W - MARGIN
    final_y = sh - H - MARGIN - TBR
    start_y = final_y + LIFT

    accent   = RED  if is_error else CYAN
    icon_chr = "⚠"  if is_error else "✓"

    # ── Создаём окно ─────────────────────────────────────────────────────────
    toast = tk.Toplevel(root)
    _toast_ref[0] = toast
    toast.overrideredirect(True)
    toast.attributes("-topmost", True)
    toast.configure(bg=BORDER)   # BORDER виден как 1px рамка через padx/pady
    toast.resizable(False, False)
    toast.geometry(f"{W}x{H}+{final_x}+{start_y}")

    # ── Обработчики закрытия и клика — определяются до построения виджетов ──
    def _close():
        if _toast_ref[0] is toast:
            _toast_ref[0] = None
        try:
            toast.destroy()
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

    def _handle_click(event=None):
        _close()
        if on_click is not None:
            try:
                root.after(0, on_click)
            except Exception:
                try:
                    on_click()
                except Exception:
                    logger.debug("Suppressed exception", exc_info=True)

    # ── Внутренний контейнер на 1px меньше со всех сторон ───────────────────
    _body_cursor = "hand2" if on_click is not None else ""
    outer = tk.Frame(toast, bg=BG, cursor=_body_cursor)
    outer.pack(fill="both", expand=True, padx=1, pady=1)
    if on_click is not None:
        outer.bind("<Button-1>", _handle_click)

    # Левая цветная полоса
    tk.Frame(outer, bg=accent, width=BAR).pack(side="left", fill="y")

    # Контентная область (отступы масштабированы)
    body_frame = tk.Frame(outer, bg=BG, padx=PX, pady=PY, cursor=_body_cursor)
    body_frame.pack(side="left", fill="both", expand=True)
    if on_click is not None:
        body_frame.bind("<Button-1>", _handle_click)

    # ── Заголовочная строка ──────────────────────────────────────────────────
    head = tk.Frame(body_frame, bg=BG, cursor=_body_cursor)
    head.pack(fill="x")
    if on_click is not None:
        head.bind("<Button-1>", _handle_click)

    tk.Label(
        head, text=icon_chr, bg=BG, fg=accent,
        font=(FONT_FAMILY, 13, "bold")         # pt-размер — ОС масштабирует сама
    ).pack(side="left", padx=(0, int(7 * sc)))

    tk.Label(
        head, text="Job Hunter AI", bg=BG, fg=TITLE,
        font=(FONT_FAMILY, 11, "bold")
    ).pack(side="left")

    close_btn = tk.Label(
        head, text="×", bg=BG, fg=MUTED,
        font=(FONT_FAMILY, 14), cursor="hand2"
    )
    close_btn.pack(side="right", padx=(int(6 * sc), 0))
    close_btn.bind("<Button-1>", lambda e: _close())

    # ── Текст сообщения ───────────────────────────────────────────────────────
    msg_lbl = tk.Label(
        body_frame, text=message, bg=BG, fg=BODY,
        font=(FONT_FAMILY, 10), anchor="w", justify="left",
        wraplength=W - int(60 * sc),            # wraplength в физических px
        cursor=_body_cursor,
    )
    msg_lbl.pack(fill="x", pady=(int(5 * sc), 0))
    if on_click is not None:
        msg_lbl.bind("<Button-1>", _handle_click)

    # ── Анимация: быстрый ease-out снизу вверх (как Telegram) ───────────────
    def _slide(cur_y: int):
        if not toast.winfo_exists():
            return
        dist = cur_y - final_y
        if dist <= 2:
            toast.geometry(f"{W}x{H}+{final_x}+{final_y}")
            toast.after(5000, lambda: _fade_out_instance(1.0))
            return
        step  = max(4, dist // 2)
        new_y = cur_y - step
        toast.geometry(f"{W}x{H}+{final_x}+{new_y}")
        toast.after(10, lambda: _slide(new_y))

    # ── Анимация: плавное угасание (instance-bound, isolated from global state) ──
    # Captures `toast` directly so _fade_out_instance is not affected by later
    # mutations of _toast_ref[0] caused by a concurrent second notification.
    def _fade_out_instance(alpha: float = 1.0):
        try:
            exists = toast.winfo_exists()
        except Exception:
            return
        if not exists:
            return
        alpha -= 0.075   # 25 % larger step → 25 % fewer frames → 25 % faster fade
        if alpha <= 0.0:
            try:
                toast.destroy()
            except Exception:
                logger.debug("Suppressed exception", exc_info=True)
            # Nullify the global reference only if it still points to this exact instance.
            if _toast_ref[0] is toast:
                _toast_ref[0] = None
            return
        try:
            toast.attributes("-alpha", alpha)
            toast.after(22, lambda: _fade_out_instance(alpha))
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

    # Звук в фоновом потоке (не блокирует UI)
    threading.Thread(target=_play_sound, args=(is_error,), daemon=True).start()
    _slide(start_y)


def send_notification(title: str, message: str, root=None, on_click=None,
                      is_error: bool | None = None) -> None:
    """
    Показывает уведомление.
    root → встроенный тост с правильным DPI-масштабированием.
    Без root → системное уведомление через plyer / win10toast (fallback).
    on_click → вызывается при клике по телу тоста (только для встроенного тоста).
    is_error → явно задаёт стиль (ошибка/успех). Если None — определяется
               эвристически по подстрокам, но вызывающему коду следует
               передавать флаг явно, т.к. эвристика хрупкая
               (например, 'error-free' ложно распознаётся как ошибка).
    """
    if is_error is None:
        is_error = (
            "ошибк" in message.lower()
            or "error" in message.lower()
            or "ошибк" in title.lower()
        )

    if root is not None:
        try:
            root.after(0, lambda: _build_toast_safe(root, message, is_error, on_click))
            return
        except Exception:
            logger.debug("Suppressed exception", exc_info=True)

    # ── Fallback на системные уведомления ────────────────────────────────────
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="Job Hunter AI", timeout=5)
        return
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=5, threaded=True)
    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
