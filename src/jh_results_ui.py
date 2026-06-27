# jh_results_ui.py
import os
import sys
import webbrowser
import customtkinter as ctk
import jh_storage_manager as storage_manager
import jh_i18n
from jh_i18n import tr
from tkinter import messagebox

from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")
LOGO_PNG_PATH = os.path.join(BASE_DIR, "logo.png")


def _load_logo_image(height_px=22):
    try:
        source = LOGO_PNG_PATH if os.path.exists(LOGO_PNG_PATH) else (ICON_PATH if os.path.exists(ICON_PATH) else None)
        if not source:
            return None
        img = Image.open(source)
        aspect = img.width / img.height
        w = int(height_px * aspect)
        img = img.resize((w, height_px), Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(w, height_px))
    except Exception:
        return None

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

def force_dark_title_bar(window):
    """Принудительно красит заголовок окна в темный цвет Windows"""
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if hwnd == 0: 
            hwnd = window.winfo_id()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception:
        pass

def _show_with_icon(window, width, height, parent=None, grab=False):
    """
    Shows a CTkToplevel with proper Windows icon support.
    Pattern: alpha=0 → geometry → deiconify (HWND created) → after(50): icon + alpha=1.
    Call this from window.after(80+, ...) so all UI widgets are already packed.
    """
    if not window.winfo_exists():
        return
    try:
        window.attributes("-alpha", 0.0)
    except Exception:
        pass
    try:
        window.update_idletasks()
        try:
            sc = window._get_window_scaling()
        except Exception:
            sc = 1.0
        # width/height логические → физические для арифметики центрирования
        child_phys_w = width * sc
        child_phys_h = height * sc
        # winfo_* возвращают физические пиксели; x/y передаём в geometry() тоже физическими
        if parent and parent.winfo_exists():
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = int(px + (pw - child_phys_w) / 2)
            y = int(py + (ph - child_phys_h) / 2)
        else:
            x = int((window.winfo_screenwidth() - child_phys_w) / 2)
            y = int((window.winfo_screenheight() - child_phys_h) / 2)
        # width/height — логические (CTk умножит на sc); x/y — физические (CTk не трогает)
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
    except Exception:
        window.geometry(f"{width}x{height}")
    window.deiconify()
    if grab:
        window.grab_set()
    window.focus_force()

    def _apply_icon():
        """Применяет иконку через iconbitmap + Win32 API. Вызывается дважды."""
        if not window.winfo_exists():
            return
        if not os.path.exists(ICON_PATH):
            return
        try:
            window.iconbitmap(ICON_PATH)
        except Exception:
            pass
        try:
            import ctypes
            # GA_ROOT(2) поднимается по цепочке родителей до корневого окна —
            # надёжно работает даже когда CTkToplevel вложен в другой CTkToplevel.
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

    def _finalize():
        if not window.winfo_exists():
            return
        _apply_icon()
        try:
            window.attributes("-alpha", 1.0)
        except Exception:
            pass
        # Повторное применение на случай если CTk сбросил иконку в своих after()-коллбэках
        window.after(350, _apply_icon)

    window.after(100, _finalize)

def center_window(window, width, height, parent=None):
    """
    Центрирует окно без мерцания (alpha=0 → geometry → alpha=1).

    Координатная модель CustomTkinter + DPI-aware Windows:
      • winfo_* — физические пиксели.
      • geometry("WxH+X+Y"): CTk масштабирует W и H, но X/Y передаёт ОС как есть.
      Формула: переводим логические w/h в физические (× sc), считаем X/Y
      в физических пикселях, передаём в geometry() без изменений.
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

            # Логические размеры → физические для арифметики центрирования
            child_phys_w = width * sc
            child_phys_h = height * sc

            if parent and parent.winfo_exists():
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

def speed_up_scroll_frame(scroll_frame, speed_multiplier=3):
    """Оптимизирует скорость прокрутки колесиком мыши для CTkScrollableFrame."""
    try:
        canvas = scroll_frame._parent_canvas
        canvas.configure(yscrollincrement=16)
        
        def _on_mousewheel(event):
            try:
                y_view = canvas.yview()
                if y_view[0] <= 0.01 and y_view[1] >= 0.99:
                    return "break"
                
                delta = int(-1 * (event.delta / 120) * speed_multiplier)
                
                if delta < 0 and y_view[0] <= 0.0:
                    return "break"
                if delta > 0 and y_view[1] >= 1.0:
                    return "break"
                
                canvas.yview_scroll(delta, "units")
            except Exception:
                pass
            return "break"
            
        canvas.bind("<MouseWheel>", _on_mousewheel, add="+")
        scroll_frame._container.bind("<MouseWheel>", _on_mousewheel, add="+")
    except Exception as e:
        print(f"[Scroll Speedup Failed]: {e}")

def open_browser_link(url):
    """Безопасно открывает ссылку в браузере по умолчанию"""
    if url and url != "#":
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Error", tr("link_error", e=e))
    else:
        messagebox.showinfo("Info", tr("no_link"))

def open_window(parent_window):
    """Создает независимое окно со списком одобренных и отклоненных вакансий"""
    jh_i18n.set_language(storage_manager.load_config().get("language", "en"))

    window = ctk.CTkToplevel(parent_window)
    window.withdraw()
    window.title(tr("results_title"))
    window.configure(fg_color=COLOR_BG_DARK)
    
    force_dark_title_bar(window)
    # Window is shown at the end via _show_with_icon — all UI must be packed first.

    window.last_approved_count = -1
    window.last_rejected_count = -1
    window.current_tab = "APPROVED"

    # Реестры уже отрисованных карточек по уникальному ключу (url).
    # Нужны для дифференциального обновления без полного destroy() всего фрейма,
    # что устраняет мерцание и сброс позиции скролла.
    # Структура: { url: {"card": <CTkFrame>, "data": <dict с данными вакансии>} }
    window.approved_cards = {}
    window.rejected_cards = {}
    # Ссылки на лейблы-заглушки "список пуст", чтобы корректно их показывать/прятать.
    window.approved_empty_lbl = None
    window.rejected_empty_lbl = None
    # Кэш последних применённых значений UI-виджетов. Нужен, чтобы НЕ дёргать
    # .configure() на каждом тике таймера: повторный configure сбрасывает внутренний
    # hover-статус CustomTkinter (кнопка "тухнет" под курсором) и заставляет
    # CTkSegmentedButton перестраивать дочерние кнопки (визуальная вспышка).
    # Перерисовываем виджет только когда его реальное значение изменилось.
    window.last_clear_btn_state = None      # "normal" | "disabled"
    window.last_tab_values = None           # tuple подписей сегментов
    window.last_tab_selected = None         # выбранная подпись сегмента

    scroll_frame_approved = ctk.CTkScrollableFrame(window, width=640, height=640, fg_color=COLOR_BG_DARK)
    scroll_frame_rejected = ctk.CTkScrollableFrame(window, width=640, height=640, fg_color=COLOR_BG_DARK)

    speed_up_scroll_frame(scroll_frame_approved)
    speed_up_scroll_frame(scroll_frame_rejected)

    logo_header = ctk.CTkFrame(window, fg_color="transparent")
    logo_header.pack(pady=(10, 0), padx=15)
    _logo = _load_logo_image(22)
    if _logo:
        ctk.CTkLabel(logo_header, image=_logo, text="").pack(side="left", padx=(0, 8))
    ctk.CTkLabel(
        logo_header,
        text="JOB HUNTER AI",
        font=("Arial", 14, "bold"),
        text_color=COLOR_CYAN_NEON
    ).pack(side="left")

    controls_header = ctk.CTkFrame(window, fg_color="transparent")
    controls_header.pack(pady=(4, 4), padx=15, fill="x")

    controls_header.columnconfigure(0, weight=1, uniform="side_cols")
    controls_header.columnconfigure(1, weight=2, uniform="mid_col")
    controls_header.columnconfigure(2, weight=1, uniform="side_cols")

    status_indicator = ctk.CTkLabel(
        controls_header,
        text="",
        font=("Arial", 11, "bold"),
        text_color=COLOR_CYAN_NEON,
        anchor="w"
    )
    status_indicator.grid(row=0, column=0, sticky="w")

    # Динамический индикатор: мигает при активном ассистенте, статичен иначе.
    _blink_dots = ("●", "○")
    _blink_idx = [0]
    _monitor_timer = [None]  # Track timer ID so we can cancel on window destroy

    def _update_monitoring():
        if not window.winfo_exists():
            return
        base = tr("monitoring")
        try:
            is_active = parent_window.is_active
            is_paused = getattr(parent_window, "_paused_mode", False)
        except Exception:
            is_active = False
            is_paused = False

        if is_active:
            dot = _blink_dots[_blink_idx[0] % 2]
            _blink_idx[0] += 1
            color = COLOR_CYAN_NEON
            delay = 1200
        elif is_paused:
            dot = "◐"
            color = COLOR_GOLD
            delay = 2000
        else:
            dot = "○"
            color = COLOR_RED
            delay = 2000

        try:
            status_indicator.configure(text=f"{dot} {base}", text_color=color)
        except Exception:
            return
        _monitor_timer[0] = window.after(delay, _update_monitoring)

    def _on_results_close():
        if _monitor_timer[0] is not None:
            try:
                window.after_cancel(_monitor_timer[0])
            except Exception:
                pass
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", _on_results_close)
    window.after(50, _update_monitoring)

    def clear_all():
        if window.current_tab == "APPROVED":
            ans = messagebox.askyesno(
                tr("clear_title"),
                tr("clear_approved_q"),
                parent=window
            )
            if ans:
                storage_manager.clear_all_vacancies()
                refresh_list(force=True)
        else:
            ans = messagebox.askyesno(
                tr("clear_title"),
                tr("clear_rejected_q"),
                parent=window
            )
            if ans:
                storage_manager.clear_all_rejected()
                refresh_list(force=True)

        window.lift()
        window.focus_force()

    btn_clear_all = ctk.CTkButton(
        controls_header,
        text=tr("btn_clear"),
        fg_color=COLOR_INPUT_BG,
        hover_color=COLOR_RED,
        text_color=COLOR_TEXT_LIGHT,
        font=("Arial", 11, "bold"),
        height=32,
        width=135,
        border_width=0,
        command=clear_all
    )
    btn_clear_all.grid(row=0, column=2, sticky="e")

    # Кэш текущих подписей вкладок для language-independent детекции нажатия.
    # Сравниваем value == window._tab_approved_text, не ищем подстроку.
    window._tab_approved_text = tr("tab_approved", n=0)
    window._tab_rejected_text = tr("tab_rejected", n=0)

    def segment_changed(value):
        window.last_tab_selected = value
        # Сравниваем по префиксу до первого "(" — счётчик меняется, основной текст нет.
        approved_prefix = window._tab_approved_text.split("(")[0]
        if value.startswith(approved_prefix):
            window.current_tab = "APPROVED"
            scroll_frame_rejected.pack_forget()
            scroll_frame_approved.pack(pady=(5, 5), padx=15, fill="both", expand=True)
            try:
                scroll_frame_approved._parent_canvas.yview_moveto(0)
            except Exception as e:
                print(f"[Results UI]: yview_moveto (approved) пропущен: {e}")
        else:
            window.current_tab = "REJECTED"
            scroll_frame_approved.pack_forget()
            scroll_frame_rejected.pack(pady=(5, 5), padx=15, fill="both", expand=True)
            try:
                scroll_frame_rejected._parent_canvas.yview_moveto(0)
            except Exception as e:
                print(f"[Results UI]: yview_moveto (rejected) пропущен: {e}")

        refresh_list(force=False)

    tab_segment = ctk.CTkSegmentedButton(
        controls_header,
        values=[tr("tab_approved", n=0), tr("tab_rejected", n=0)],
        font=("Arial", 11, "bold"),
        command=segment_changed,
        selected_color=COLOR_GOLD,
        selected_hover_color=COLOR_GOLD_HOVER,
        text_color=COLOR_TEXT_LIGHT,
        fg_color=COLOR_CARD_BG,
        height=32
    )
    tab_segment.grid(row=0, column=1, sticky="ew")

    # Stats bar: total counts + session counts
    stats_lbl = ctk.CTkLabel(
        controls_header,
        text="",
        font=("Arial", 10),
        text_color=COLOR_TEXT_MUTED,
        anchor="w"
    )
    stats_lbl.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

    scroll_frame_approved.pack(pady=(5, 5), padx=15, fill="both", expand=True)

    def build_approved_card(parent_frame, item):
        company = item.get("company", "Не указана")
        title = item.get("title", "Не указано")
        url = item.get("url", "#")
        cover_letter = item.get("cover_letter", "")

        card = ctk.CTkFrame(parent_frame, fg_color=COLOR_CARD_BG, corner_radius=8, border_width=1, border_color=COLOR_INPUT_BG)
        card.pack(pady=4, padx=5, fill="x")

        info_text = f"🏢 {company}\n💼 {title}"
        info_lbl = ctk.CTkLabel(
            card, text=info_text, font=("Arial", 13, "bold"), 
            anchor="w", justify="left", text_color=COLOR_TEXT_LIGHT, wraplength=340
        )
        info_lbl.pack(side="left", padx=12, pady=8, fill="x", expand=True)

        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=6)

        btn_letter = ctk.CTkButton(
            btn_frame, text=tr("btn_letter"), width=85, height=32,
            fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_TEXT_MUTED,
            border_width=0,
            command=lambda: show_letter_window(window, title, company, cover_letter)
        )
        btn_letter.grid(row=0, column=0, padx=3)

        btn_apply = ctk.CTkButton(
            btn_frame, text=tr("btn_apply"), width=110, height=32,
            fg_color=COLOR_CYAN_NEON, hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK, font=("Arial", 12, "bold"),
            border_width=0,
            command=lambda: open_browser_link(url)
        )
        btn_apply.grid(row=0, column=1, padx=3)

        btn_delete = ctk.CTkButton(
            btn_frame, text="✕", width=32, height=32, corner_radius=6,
            fg_color=COLOR_RED, hover_color=COLOR_RED_HOVER,
            text_color=COLOR_TEXT_LIGHT,
            font=("Arial", 12, "bold"),
            border_width=0,
            command=lambda: delete_approved_item(url)
        )
        btn_delete.grid(row=0, column=2, padx=3)

        return card

    def build_rejected_card(parent_frame, item):
        company = item.get("company", "Не указана")
        title = item.get("title", "Не указано")
        url = item.get("url", "#")
        reason = item.get("reason", "Причина не указана")

        card = ctk.CTkFrame(parent_frame, fg_color=COLOR_CARD_BG, corner_radius=8, border_width=1, border_color=COLOR_INPUT_BG)
        card.pack(pady=4, padx=5, fill="x")

        info_text = f"🏢 {company} | 💼 {title}\n"
        info_lbl = ctk.CTkLabel(
            card, text=info_text, font=("Arial", 13, "bold"), 
            anchor="w", justify="left", text_color=COLOR_RED
        )
        info_lbl.pack(anchor="w", padx=15, pady=(8, 2))

        reason_lbl = ctk.CTkLabel(
            card, text=f"✕ {reason}", font=("Arial", 12),
            anchor="w", justify="left", text_color=COLOR_TEXT_MUTED, wraplength=580
        )
        reason_lbl.pack(anchor="w", padx=15, pady=(0, 8), fill="x", expand=True)

        opt_frame = ctk.CTkFrame(card, fg_color="transparent")
        opt_frame.pack(anchor="e", padx=15, pady=(0, 8))

        btn_anyway = ctk.CTkButton(
            opt_frame, text=tr("btn_anyway"), width=170, height=28, corner_radius=6,
            fg_color=COLOR_GOLD, hover_color=COLOR_GOLD_HOVER,
            text_color=COLOR_BG_DARK,
            font=("Arial", 11, "bold"),
            border_width=0,
            command=lambda: open_browser_link(url)
        )
        btn_anyway.pack(side="left", padx=5)

        btn_delete_rej = ctk.CTkButton(
            opt_frame, text=tr("btn_delete_rej"), width=150, height=28, corner_radius=6,
            fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_TEXT_LIGHT,
            font=("Arial", 11),
            border_width=0,
            command=lambda: delete_rejected_item(url)
        )
        btn_delete_rej.pack(side="left", padx=5)

        return card

    def _vacancy_signature(item, kind):
        """
        Строит сигнатуру содержимого карточки. Если данные вакансии с тем же url
        изменились (например, переписалось письмо или причина), сигнатура изменится,
        и карточка будет пересоздана. Если нет — карточка остаётся нетронутой.
        """
        if kind == "APPROVED":
            return (
                item.get("company", ""),
                item.get("title", ""),
                item.get("cover_letter", ""),
            )
        return (
            item.get("company", ""),
            item.get("title", ""),
            item.get("reason", ""),
        )

    def _sync_cards(scroll_frame, items, registry, kind):
        """
        Дифференциально синхронизирует карточки во фрейме со списком items.
          - удаляет карточки, которых больше нет в БД (по url);
          - добавляет новые;
          - пересоздаёт только те, у кого изменилось содержимое;
          - неизменившиеся оставляет на месте (скролл и позиция сохраняются).
        Возвращает True, если фрейм визуально изменился (что-то добавлено/удалено).
        """
        builder = build_approved_card if kind == "APPROVED" else build_rejected_card
        empty_text = tr("empty_approved") if kind == "APPROVED" else tr("empty_rejected")

        # Карта актуальных записей по url с сохранением порядка следования из БД.
        desired = {}
        order = []
        for item in items:
            url = item.get("url", "#")
            # При коллизии url (теоретически возможной) последняя запись побеждает.
            if url not in desired:
                order.append(url)
            desired[url] = item

        changed = False

        # 1. Удаляем карточки, которых больше нет в БД.
        for url in list(registry.keys()):
            if url not in desired:
                entry = registry.pop(url)
                try:
                    entry["card"].destroy()
                except Exception:
                    pass
                changed = True

        # 2. Добавляем новые и обновляем изменившиеся.
        for url in order:
            item = desired[url]
            sig = _vacancy_signature(item, kind)
            existing = registry.get(url)
            if existing is None:
                # Новая карточка.
                card = builder(scroll_frame, item)
                registry[url] = {"card": card, "sig": sig}
                changed = True
            elif existing.get("sig") != sig:
                # Содержимое изменилось — пересоздаём только эту карточку на её месте.
                try:
                    existing["card"].destroy()
                except Exception:
                    pass
                card = builder(scroll_frame, item)
                registry[url] = {"card": card, "sig": sig}
                changed = True

        # 3. Управляем лейблом-заглушкой "список пуст".
        if kind == "APPROVED":
            if not registry and window.approved_empty_lbl is None:
                window.approved_empty_lbl = ctk.CTkLabel(
                    scroll_frame, text=empty_text, font=("Arial", 14), text_color=COLOR_TEXT_MUTED
                )
                window.approved_empty_lbl.pack(pady=50)
            elif registry and window.approved_empty_lbl is not None:
                try:
                    window.approved_empty_lbl.destroy()
                except Exception:
                    pass
                window.approved_empty_lbl = None
        else:
            if not registry and window.rejected_empty_lbl is None:
                window.rejected_empty_lbl = ctk.CTkLabel(
                    scroll_frame, text=empty_text, font=("Arial", 14), text_color=COLOR_TEXT_MUTED
                )
                window.rejected_empty_lbl.pack(pady=50)
            elif registry and window.rejected_empty_lbl is not None:
                try:
                    window.rejected_empty_lbl.destroy()
                except Exception:
                    pass
                window.rejected_empty_lbl = None

        return changed

    def update_clear_button_state(approved, rejected):
        """
        Актуализирует доступность кнопки 'Очистить список' строго по содержимому
        ТЕКУЩЕЙ активной вкладки. Вызывается ДО любого раннего return, чтобы при
        переключении вкладок состояние кнопки всегда было корректным.

        ВАЖНО: реально вызывает .configure() ТОЛЬКО когда состояние изменилось.
        Это убирает баг "потухающего" hover-эффекта: при каждом тике таймера
        повторный configure(state=...) сбрасывал внутренний hover-статус
        CustomTkinter, и подсветка кнопки гасла прямо под курсором.
        """
        current_list = approved if window.current_tab == "APPROVED" else rejected
        desired_state = "normal" if current_list else "disabled"
        if desired_state == window.last_clear_btn_state:
            return  # Состояние не изменилось — не трогаем виджет, hover сохраняется.
        try:
            btn_clear_all.configure(state=desired_state)
            window.last_clear_btn_state = desired_state
        except Exception as e:
            print(f"[Results UI]: Не удалось обновить состояние кнопки очистки: {e}")

    def update_tab_labels(approved, rejected):
        """
        Обновляет подписи и выбранный сегмент переключателя вкладок.
        Тоже работает через кэш: configure(values=...) на CTkSegmentedButton
        пересоздаёт дочерние кнопки и даёт визуальную вспышку, поэтому делаем это
        только при фактическом изменении количества записей или активной вкладки.
        """
        approved_text = tr("tab_approved", n=len(approved))
        rejected_text = tr("tab_rejected", n=len(rejected))
        # Обновляем кэш префиксов для language-independent детекции
        window._tab_approved_text = tr("tab_approved", n=0)
        window._tab_rejected_text = tr("tab_rejected", n=0)
        values = (approved_text, rejected_text)
        selected = approved_text if window.current_tab == "APPROVED" else rejected_text

        # Пересобираем список значений только если подписи реально изменились.
        if values != window.last_tab_values:
            try:
                tab_segment.configure(values=[approved_text, rejected_text])
                window.last_tab_values = values
                # После смены values принудительно переустанавливаем выбор,
                # т.к. внутренний выбор мог слететь при пересборке.
                window.last_tab_selected = None
            except Exception as e:
                print(f"[Results UI]: Не удалось обновить подписи вкладок: {e}")

        # Устанавливаем выбранный сегмент только если он реально изменился.
        if selected != window.last_tab_selected:
            try:
                tab_segment.set(selected)
                window.last_tab_selected = selected
            except Exception as e:
                print(f"[Results UI]: Не удалось установить активную вкладку: {e}")

    def _dedup_by_url(items):
        """Оставляет только первую запись для каждого URL — устраняет дубли в БД."""
        seen = {}
        for item in items:
            url = item.get("url", "#")
            if url not in seen:
                seen[url] = item
        return list(seen.values())

    def refresh_list(force=False, _preloaded=None):
        """
        Дифференциально обновляет списки вакансий без полного уничтожения карточек.
        _preloaded: (approved, rejected) tuple pre-fetched from a background thread.
        """
        if not window.winfo_exists():
            return

        if _preloaded is not None:
            approved, rejected = _preloaded
        else:
            try:
                approved = _dedup_by_url(storage_manager.get_all_approved())
                rejected = _dedup_by_url(storage_manager.get_all_rejected())
            except Exception as e:
                print(f"[Ошибка чтения БД]: {e}")
                approved = []
                rejected = []

        # --- Эти обновления выполняются ВСЕГДА, даже без изменений в данных, ---
        # --- но внутри себя дёргают виджеты только при реальном изменении.    ---
        update_tab_labels(approved, rejected)

        # Критично: состояние кнопки очистки актуализируется до возможного return.
        update_clear_button_state(approved, rejected)

        # Stats bar
        try:
            n_a, n_r = len(approved), len(rejected)
            total = n_a + n_r
            rate_str = f"{100 * n_a // total}%" if total > 0 else "—"
            sess_a = getattr(parent_window, "_session_approved", 0)
            sess_r = getattr(parent_window, "_session_rejected", 0)
            stats_lbl.configure(
                text=f"✓ {n_a}  ✕ {n_r}  ◑ {rate_str} rate  │  session +{sess_a} / ✕{sess_r}"
            )
        except Exception:
            pass
        # ----------------------------------------------------------------------

        approved_changed = (len(approved) != window.last_approved_count)
        rejected_changed = (len(rejected) != window.last_rejected_count)

        # Если ничего не поменялось и обновление не принудительное — выходим,
        # но кнопка и подписи уже корректно обновлены выше.
        if not force and not approved_changed and not rejected_changed:
            return

        # Синхронизируем карточки дифференциально (без мерцания).
        _sync_cards(scroll_frame_approved, approved, window.approved_cards, "APPROVED")
        _sync_cards(scroll_frame_rejected, rejected, window.rejected_cards, "REJECTED")

        window.last_approved_count = len(approved)
        window.last_rejected_count = len(rejected)

    def auto_refresh_loop():
        if not window.winfo_exists():
            return
        # Читаем БД в фоновом потоке, чтобы не блокировать UI во время файлового I/O
        import threading as _threading
        def _bg_read():
            try:
                a = _dedup_by_url(storage_manager.get_all_approved())
                r = _dedup_by_url(storage_manager.get_all_rejected())
            except Exception:
                a, r = [], []
            def _apply():
                if window.winfo_exists():
                    refresh_list(force=False, _preloaded=(a, r))
            # Двойная проверка: window может быть уничтожено пока поток читал БД.
            # winfo_exists() + try/except защищает от TclError при вызове after()
            # из фонового потока после закрытия окна.
            try:
                if window.winfo_exists():
                    window.after(0, _apply)
            except Exception:
                pass
        _threading.Thread(target=_bg_read, daemon=True).start()
        window.after(3000, auto_refresh_loop)

    def delete_approved_item(url):
        storage_manager.delete_vacancy_by_url(url)
        refresh_list(force=True)

    def delete_rejected_item(url):
        storage_manager.delete_rejected_by_url(url)
        refresh_list(force=True)

    refresh_list(force=True)
    auto_refresh_loop()

    # Show window after all UI is packed — correct Windows HWND + icon pattern
    window.after(120, lambda: _show_with_icon(window, 680, 750, parent_window, grab=False))

def show_letter_window(parent, title, company, cover_letter):
    """Детальный просмотр сгенерированного письма"""
    top = ctk.CTkToplevel(parent)
    top.withdraw()
    top.title(tr("letter_win_title"))
    top.configure(fg_color=COLOR_BG_DARK)

    force_dark_title_bar(top)
    # Icon + geometry set via _show_with_icon after UI is built

    letter_header = ctk.CTkFrame(top, fg_color="transparent")
    letter_header.pack(pady=(15, 4), padx=20)
    _letter_logo = _load_logo_image(22)
    if _letter_logo:
        ctk.CTkLabel(letter_header, image=_letter_logo, text="").pack(side="left", padx=(0, 8))
    ctk.CTkLabel(
        letter_header,
        text=tr("letter_win_title"),
        font=("Arial", 14, "bold"),
        text_color=COLOR_CYAN_NEON
    ).pack(side="left")

    ctk.CTkLabel(
        top,
        text=f"{title} — {company}",
        font=("Arial", 12),
        text_color=COLOR_TEXT_MUTED,
        justify="center",
        wraplength=580
    ).pack(padx=20, pady=(0, 6))

    content_box = ctk.CTkTextbox(
        top, font=("Arial", 13), width=580, height=360,
        fg_color=COLOR_INPUT_BG, text_color=COLOR_TEXT_LIGHT,
        border_width=1, border_color=COLOR_CARD_BG
    )
    content_box.pack(pady=10, padx=20)
    content_box.insert("0.0", cover_letter if cover_letter else "—")

    bind_russian_hotkeys(content_box)

    def copy_to_clipboard():
        top.clipboard_clear()
        top.clipboard_append(content_box.get("0.0", "end-1c"))
        btn_copy.configure(text=tr("copied_ok_text"), fg_color=COLOR_CYAN_HOVER, text_color=COLOR_TEXT_LIGHT)
        top.after(2000, lambda: btn_copy.configure(text=tr("btn_copy"), fg_color=COLOR_CYAN_NEON, text_color=COLOR_BG_DARK))

    btn_copy = ctk.CTkButton(
        top, text=tr("btn_copy"),
        command=copy_to_clipboard, fg_color=COLOR_CYAN_NEON, text_color=COLOR_BG_DARK,
        height=42, font=("Arial", 13, "bold"), hover_color=COLOR_CYAN_HOVER,
        border_width=0
    )
    btn_copy.pack(pady=15)

    top.after(120, lambda: _show_with_icon(top, 640, 600, parent, grab=False))