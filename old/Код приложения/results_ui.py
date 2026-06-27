# results_ui.py
import os
import sys
import webbrowser
import customtkinter as ctk
import storage_manager
from tkinter import messagebox

# Получаем абсолютный путь к папке проекта, чтобы иконка не терялась
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")

# Новая мягкая космическая палитра (без вырвиглазного контраста)
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

def set_window_icon(window):
    """Безопасная установка иконки программы"""
    try:
        if os.path.exists(ICON_PATH):
            window.after(200, lambda: window.iconbitmap(ICON_PATH))
        else:
            window.after(200, lambda: window.iconbitmap(sys.executable))
    except Exception:
        pass

def center_window(window, width, height, parent=None):
    """
    Абсолютно безопасная функция центрирования окон для High-DPI экранов.
    Использует withdraw/deiconify вместо прозрачности альфа-канала для предотвращения мерцания.
    """
    try:
        window.withdraw()
    except Exception:
        pass
    
    def _apply_centered_position():
        if not window.winfo_exists():
            return
        try:
            window.update_idletasks()
            try:
                scaling = window._get_window_scaling()
            except Exception:
                scaling = 1.0

            scaled_width = int(width * scaling)
            scaled_height = int(height * scaling)
            
            if parent and parent.winfo_exists():
                parent_x = parent.winfo_x()
                parent_y = parent.winfo_y()
                parent_w = parent.winfo_width()
                parent_h = parent.winfo_height()
                
                x = parent_x + (parent_w - scaled_width) // 2
                y = parent_y + (parent_h - scaled_height) // 2
            else:
                screen_width = window.winfo_screenwidth()
                screen_height = window.winfo_screenheight()
                
                x = (screen_width - scaled_width) // 2
                y = (screen_height - scaled_height) // 2
            
            x = max(0, int(x))
            y = max(0, int(y))
            
            window.geometry(f"{width}x{height}+{x}+{y}")
        except Exception as e:
            print(f"[Резервное центрирование]: {e}")
            window.geometry(f"{width}x{height}")
        finally:
            try:
                window.deiconify()
            except Exception:
                pass
        
    window.after(10, _apply_centered_position)

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

def speed_up_scroll_frame(scroll_frame, speed_multiplier=3):
    """
    Оптимизирует скорость прокрутки колесиком мыши для CTkScrollableFrame.
    Блокирует уход в отрицательные координаты и бесконечную прокрутку на пустых/коротких списках.
    """
    try:
        canvas = scroll_frame._parent_canvas
        canvas.configure(yscrollincrement=16)
        
        def _on_mousewheel(event):
            try:
                # Получаем текущие границы видимой области [0.0, 1.0]
                y_view = canvas.yview()
                
                # Если весь контент свободно помещается на одном экране, отключаем скроллинг
                if y_view[0] <= 0.01 and y_view[1] >= 0.99:
                    return "break"
                
                # Вычисляем направление и шаг прокрутки
                delta = int(-1 * (event.delta / 120) * speed_multiplier)
                
                # Препятствуем уходу скролла за верхнюю границу
                if delta < 0 and y_view[0] <= 0.0:
                    return "break"
                # Препятствуем уходу скролла за нижнюю границу
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
            messagebox.showerror("Ошибка", f"Не удалось открыть ссылку: {e}")
    else:
        messagebox.showinfo("Информация", "Ссылка на вакансию отсутствует.")

def open_window(parent_window):
    """Создает независимое окно со списком одобренных и отклоненных вакансий"""
    window = ctk.CTkToplevel(parent_window)
    window.title("Результаты анализа ИИ")
    window.configure(fg_color=COLOR_BG_DARK)
    
    force_dark_title_bar(window)
    set_window_icon(window)
    
    center_window(window, 680, 750, parent_window)
    window.focus()

    window.last_approved_count = -1
    window.last_rejected_count = -1
    window.current_tab = "APPROVED"  # "APPROVED" или "REJECTED"

    # Создаем две РАЗДЕЛЬНЫЕ скроллируемые области для предотвращения мерцания при смене вкладок
    scroll_frame_approved = ctk.CTkScrollableFrame(window, width=640, height=640, fg_color=COLOR_BG_DARK)
    scroll_frame_rejected = ctk.CTkScrollableFrame(window, width=640, height=640, fg_color=COLOR_BG_DARK)

    speed_up_scroll_frame(scroll_frame_approved)
    speed_up_scroll_frame(scroll_frame_rejected)

    # Верхний горизонтальный контейнер для объединенного управления
    controls_header = ctk.CTkFrame(window, fg_color="transparent")
    controls_header.pack(pady=(12, 4), padx=15, fill="x")

    # Сетка из 3-х колонок для идеального центрирования
    # Колонка 0 (слева) и Колонка 2 (справа) занимают строго одинаковую ширину side_cols
    controls_header.columnconfigure(0, weight=1, uniform="side_cols")
    controls_header.columnconfigure(1, weight=2, uniform="mid_col")
    controls_header.columnconfigure(2, weight=1, uniform="side_cols")

    # Левая колонка: Стильный индикатор статуса программы для визуальной симметрии
    status_indicator = ctk.CTkLabel(
        controls_header, 
        text="● Мониторинг ИИ", 
        font=("Arial", 11, "bold"), 
        text_color=COLOR_CYAN_NEON,
        anchor="w"
    )
    status_indicator.grid(row=0, column=0, sticky="w")

    # Функция очистки списков
    def clear_all():
        if window.current_tab == "APPROVED":
            if messagebox.askyesno("Очистка базы данных", "Вы уверены, что хотите безвозвратно удалить ВСЕ одобренные вакансии из списка?"):
                storage_manager.clear_all_vacancies()
                refresh_list(force=True)
        else:
            if messagebox.askyesno("Очистка базы данных", "Вы уверены, что хотите очистить весь журнал отклоненных вакансий?"):
                storage_manager.clear_all_rejected()
                refresh_list(force=True)

    # Правая колонка: Компактная кнопка очистки, симметричная левому статусу
    btn_clear_all = ctk.CTkButton(
        controls_header, 
        text="🗑️ Очистить список", 
        fg_color=COLOR_CARD_BG, 
        hover_color=COLOR_RED, 
        border_color=COLOR_RED,
        border_width=1,
        text_color=COLOR_TEXT_LIGHT,
        font=("Arial", 11, "bold"),
        height=32,
        width=130,
        command=clear_all
    )
    btn_clear_all.grid(row=0, column=2, sticky="e")

    def segment_changed(value):
        if "Одобренные" in value:
            window.current_tab = "APPROVED"
            scroll_frame_rejected.pack_forget()
            scroll_frame_approved.pack(pady=(5, 5), padx=15, fill="both", expand=True)
            
            try:
                scroll_frame_approved._parent_canvas.yview_moveto(0)
            except Exception:
                pass
        else:
            window.current_tab = "REJECTED"
            scroll_frame_approved.pack_forget()
            scroll_frame_rejected.pack(pady=(5, 5), padx=15, fill="both", expand=True)
            
            try:
                scroll_frame_rejected._parent_canvas.yview_moveto(0)
            except Exception:
                pass
            
        refresh_list(force=False)

    # Центральная колонка: Переключатель вкладок, спозиционированный строго по центру
    tab_segment = ctk.CTkSegmentedButton(
        controls_header, 
        values=["Одобренные ИИ 👍", "Отклоненные ИИ ✕"], 
        font=("Arial", 11, "bold"), 
        command=segment_changed,
        selected_color=COLOR_GOLD, 
        selected_hover_color=COLOR_GOLD_HOVER,
        text_color=COLOR_TEXT_LIGHT,
        fg_color=COLOR_CARD_BG,
        height=32
    )
    tab_segment.grid(row=0, column=1, sticky="ew")

    # По умолчанию пакуем одобренный фрейм
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

        # Невзрачная, аккуратная кнопка "Письмо"
        btn_letter = ctk.CTkButton(
            btn_frame, text="✍️ Письмо", width=85, 
            fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_TEXT_MUTED,
            border_width=1, border_color=COLOR_INPUT_BG,
            command=lambda: show_letter_window(window, title, company, cover_letter)
        )
        btn_letter.grid(row=0, column=0, padx=3)

        # Кнопка "Откликнуться"
        btn_apply = ctk.CTkButton(
            btn_frame, text="🚀 Откликнуться", width=110, 
            fg_color=COLOR_CYAN_NEON, hover_color=COLOR_CYAN_HOVER,
            text_color=COLOR_BG_DARK, font=("Arial", 12, "bold"),
            command=lambda: open_browser_link(url)
        )
        btn_apply.grid(row=0, column=1, padx=3)

        # Кнопка удаления
        btn_delete = ctk.CTkButton(
            btn_frame, text="✕", width=32, height=32, corner_radius=6,
            fg_color=COLOR_RED, hover_color=COLOR_RED_HOVER,
            text_color=COLOR_TEXT_LIGHT,
            font=("Arial", 12, "bold"),
            command=lambda: delete_approved_item(url)
        )
        btn_delete.grid(row=0, column=2, padx=3)

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

        # Кнопка вопреки ИИ "Всё равно откликнуться"
        btn_anyway = ctk.CTkButton(
            opt_frame, text="🔗 Всё равно откликнуться", width=170, height=26, corner_radius=6,
            fg_color=COLOR_GOLD, hover_color=COLOR_GOLD_HOVER,
            text_color=COLOR_BG_DARK,
            font=("Arial", 11, "bold"),
            command=lambda: open_browser_link(url)
        )
        btn_anyway.pack(side="left", padx=5)

        # Кнопка удаления для отклоненного элемента
        btn_delete_rej = ctk.CTkButton(
            opt_frame, text="Удалить из истории ✕", width=150, height=26, corner_radius=6,
            fg_color=COLOR_CARD_BG, hover_color=COLOR_INPUT_BG,
            text_color=COLOR_TEXT_LIGHT,
            border_width=1, border_color=COLOR_INPUT_BG,
            font=("Arial", 11),
            command=lambda: delete_rejected_item(url)
        )
        btn_delete_rej.pack(side="left", padx=5)

    def refresh_list(force=False):
        """Интеллектуально перерисовывает списки вакансий только при изменении данных в БД"""
        if not window.winfo_exists():
            return

        try:
            approved = storage_manager.get_all_approved()
            rejected = storage_manager.get_all_rejected()
        except Exception as e:
            print(f"[Ошибка чтения БД]: {e}")
            approved = []
            rejected = []

        # 1. Генерируем точные текстовые строки для вкладок
        approved_text = f"Одобренные ИИ ({len(approved)}) 👍"
        rejected_text = f"Отклоненные ИИ ({len(rejected)}) ✕"

        # 2. Обновляем значения кнопок
        tab_segment.configure(values=[approved_text, rejected_text])

        # 3. ФИКС БАГА ПОДСВЕТКИ: Принудительно устанавливаем активную вкладку, чтобы кнопка горела
        if window.current_tab == "APPROVED":
            tab_segment.set(approved_text)
            btn_clear_all.configure(text="🗑️ Очистить одобренные")
        else:
            tab_segment.set(rejected_text)
            btn_clear_all.configure(text="🗑️ Очистить отклонённые")

        # Проверяем изменения для каждой вкладки отдельно
        approved_changed = force or (len(approved) != window.last_approved_count)
        rejected_changed = force or (len(rejected) != window.last_rejected_count)

        # Перерисовываем список одобренных только при реальном изменении их количества
        if approved_changed:
            window.last_approved_count = len(approved)
            for widget in scroll_frame_approved.winfo_children():
                widget.destroy()
            
            if not approved:
                empty_lbl = ctk.CTkLabel(scroll_frame_approved, text="Список одобренных вакансий пока пуст.", font=("Arial", 14), text_color=COLOR_TEXT_MUTED)
                empty_lbl.pack(pady=50)
            else:
                for item in approved:
                    build_approved_card(scroll_frame_approved, item)

        # Перерисовываем список отклоненных только при реальном изменении их количества
        if rejected_changed:
            window.last_rejected_count = len(rejected)
            for widget in scroll_frame_rejected.winfo_children():
                widget.destroy()
            
            if not rejected:
                empty_lbl = ctk.CTkLabel(scroll_frame_rejected, text="Журнал отклонений пуст.", font=("Arial", 14), text_color=COLOR_TEXT_MUTED)
                empty_lbl.pack(pady=50)
            else:
                for item in rejected:
                    build_rejected_card(scroll_frame_rejected, item)

        # Выставляем активность кнопки очистки
        current_list = approved if window.current_tab == "APPROVED" else rejected
        if not current_list:
            btn_clear_all.configure(state="disabled")
        else:
            btn_clear_all.configure(state="normal")

    def auto_refresh_loop():
        """Фоновый цикл проверки базы данных каждые 3 секунды"""
        if window.winfo_exists():
            refresh_list(force=False)
            window.after(3000, auto_refresh_loop)

    def delete_approved_item(url):
        storage_manager.delete_vacancy_by_url(url)
        refresh_list(force=True)

    def delete_rejected_item(url):
        storage_manager.delete_rejected_by_url(url)
        refresh_list(force=True)

    # Первичный рендеринг и запуск фонового обновления
    refresh_list(force=True)
    auto_refresh_loop()

def show_letter_window(parent, title, company, cover_letter):
    """Минималистичное окно детального просмотра сопроводительного письма"""
    top = ctk.CTkToplevel(parent)
    top.title("Сопроводительное письмо")
    top.configure(fg_color=COLOR_BG_DARK)
    
    force_dark_title_bar(top)
    set_window_icon(top)
    
    center_window(top, 640, 600, parent)
    top.focus()
    
    # Крупный центрированный заголовок с названием вакансии и компании
    header_text = f"Сопроводительное письмо\n{title} в {company}"
    header_label = ctk.CTkLabel(
        top, text=header_text, font=("Arial", 14, "bold"), 
        text_color=COLOR_CYAN_NEON, justify="center", wraplength=580
    )
    header_label.pack(pady=15, padx=20)
    
    # Окно вывода содержимого (только сопроводительное письмо)
    content_box = ctk.CTkTextbox(
        top, font=("Arial", 13), width=580, height=360, 
        fg_color=COLOR_INPUT_BG, text_color=COLOR_TEXT_LIGHT,
        border_width=1, border_color=COLOR_CARD_BG
    )
    content_box.pack(pady=10, padx=20)
    content_box.insert("0.0", cover_letter if cover_letter else "Письмо не было сгенерировано.")
    
    bind_russian_hotkeys(content_box)

    # Кнопка копирования контента в буфер обмена
    def copy_to_clipboard():
        top.clipboard_clear()
        top.clipboard_append(content_box.get("0.0", "end-1c"))
        btn_copy.configure(text="Успешно скопировано! ✓", fg_color=COLOR_CYAN_HOVER, text_color=COLOR_TEXT_LIGHT)
        top.after(2000, lambda: btn_copy.configure(text="Копировать письмо в буфер 📋", fg_color=COLOR_CYAN_NEON, text_color=COLOR_BG_DARK))

    btn_copy = ctk.CTkButton(
        top, text="Копировать письмо в буфер 📋", 
        command=copy_to_clipboard, fg_color=COLOR_CYAN_NEON, text_color=COLOR_BG_DARK,
        height=42, font=("Arial", 13, "bold"), hover_color=COLOR_CYAN_HOVER
    )
    btn_copy.pack(pady=15)