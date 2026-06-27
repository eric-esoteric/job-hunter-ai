# jh_notifications.py — in-app Telegram-style toast (no external dependencies)
import threading

_toast_ref = [None]   # единственный активный тост; новый вытесняет старый

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
BG     = "#111622"
BORDER = "#1D2535"
TITLE  = "#E9EDF0"
BODY   = "#B0BAC6"
MUTED  = "#6B778A"
CYAN   = "#00D8C6"
RED    = "#D24B4B"


def _get_scale(root) -> float:
    """
    Возвращает DPI scale-фактор — тот же метод, что использует главное окно.
    Приоритет: CTk-метод → Windows API → 1.0.
    """
    try:
        return root._get_window_scaling()
    except Exception:
        pass
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
        pass


def _build_toast(root, message: str, is_error: bool = False) -> None:
    """Создаёт Telegram-стайл тост в правом нижнем углу экрана."""
    import tkinter as tk

    # ── Закрываем предыдущий тост ────────────────────────────────────────────
    if _toast_ref[0] is not None:
        try:
            _toast_ref[0].destroy()
        except Exception:
            pass
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

    # ── Внутренний контейнер на 1px меньше со всех сторон ───────────────────
    outer = tk.Frame(toast, bg=BG)
    outer.pack(fill="both", expand=True, padx=1, pady=1)

    # Левая цветная полоса
    tk.Frame(outer, bg=accent, width=BAR).pack(side="left", fill="y")

    # Контентная область (отступы масштабированы)
    body_frame = tk.Frame(outer, bg=BG, padx=PX, pady=PY)
    body_frame.pack(side="left", fill="both", expand=True)

    # ── Заголовочная строка ──────────────────────────────────────────────────
    head = tk.Frame(body_frame, bg=BG)
    head.pack(fill="x")

    tk.Label(
        head, text=icon_chr, bg=BG, fg=accent,
        font=("Segoe UI", 13, "bold")          # pt-размер — ОС масштабирует сама
    ).pack(side="left", padx=(0, int(7 * sc)))

    tk.Label(
        head, text="Job Hunter AI", bg=BG, fg=TITLE,
        font=("Segoe UI", 11, "bold")
    ).pack(side="left")

    def _close():
        if _toast_ref[0] is toast:
            _toast_ref[0] = None
        try:
            toast.destroy()
        except Exception:
            pass

    close_btn = tk.Label(
        head, text="×", bg=BG, fg=MUTED,
        font=("Segoe UI", 14), cursor="hand2"
    )
    close_btn.pack(side="right", padx=(int(6 * sc), 0))
    close_btn.bind("<Button-1>", lambda e: _close())

    # ── Текст сообщения ───────────────────────────────────────────────────────
    tk.Label(
        body_frame, text=message, bg=BG, fg=BODY,
        font=("Segoe UI", 10), anchor="w", justify="left",
        wraplength=W - int(60 * sc)             # wraplength в физических px
    ).pack(fill="x", pady=(int(5 * sc), 0))

    # ── Анимация: быстрый ease-out снизу вверх (как Telegram) ───────────────
    def _slide(cur_y: int):
        if not toast.winfo_exists():
            return
        dist = cur_y - final_y
        if dist <= 2:
            toast.geometry(f"{W}x{H}+{final_x}+{final_y}")
            toast.after(5000, _fade_out)
            return
        step  = max(4, dist // 2)
        new_y = cur_y - step
        toast.geometry(f"{W}x{H}+{final_x}+{new_y}")
        toast.after(10, lambda: _slide(new_y))

    # ── Анимация: плавное угасание ────────────────────────────────────────────
    def _fade_out(alpha: float = 1.0):
        if not toast.winfo_exists():
            return
        alpha -= 0.06
        if alpha <= 0.0:
            _close()
            return
        try:
            toast.attributes("-alpha", alpha)
        except Exception:
            pass
        toast.after(22, lambda: _fade_out(alpha))

    # Звук в фоновом потоке (не блокирует UI)
    threading.Thread(target=_play_sound, args=(is_error,), daemon=True).start()
    _slide(start_y)


def send_notification(title: str, message: str, root=None) -> None:
    """
    Показывает уведомление.
    root → встроенный тост с правильным DPI-масштабированием.
    Без root → системное уведомление через plyer / win10toast (fallback).
    """
    is_error = (
        "ошибк" in message.lower()
        or "error" in message.lower()
        or "ошибк" in title.lower()
    )

    if root is not None:
        try:
            root.after(0, lambda: _build_toast(root, message, is_error))
            return
        except Exception:
            pass

    # ── Fallback на системные уведомления ────────────────────────────────────
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="Job Hunter AI", timeout=5)
        return
    except Exception:
        pass
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=5, threaded=True)
    except Exception:
        pass
