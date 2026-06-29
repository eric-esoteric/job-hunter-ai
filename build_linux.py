#!/usr/bin/env python3
"""
build_linux.py — сборщик Job Hunter AI для Linux (X11) через PyInstaller.

Использование:
    python3 build_linux.py

────────────────────────────────────────────────────────────────────────────────
СИСТЕМНЫЕ ЗАВИСИМОСТИ — требуются на каждой машине с приложением:

  Debian / Ubuntu:   sudo apt install xclip python3-tk python3-gi
                     sudo apt install gir1.2-ayatana-appindicator3-0.1
  Fedora / RHEL:     sudo dnf install xclip python3-tkinter python3-gobject
                     sudo dnf install libayatana-appindicator-gtk3
  Arch Linux:        sudo pacman -S xclip tk python-gobject
                     sudo pacman -S libayatana-appindicator

  xclip          — системный буфер обмена (pyperclip)
  python3-tk     — виджеты Tkinter (customtkinter)
  python3-gi     — PyGObject: нужен pystray для иконки в трее
  ayatana / appindicator — индикатор в панели задач (трей)
────────────────────────────────────────────────────────────────────────────────
"""
import os
import re
import sys
import subprocess
import shutil


_DEPS_NOTICE = """\
┌──────────────────────────────────────────────────────────────────────────────┐
│  СИСТЕМНЫЕ ЗАВИСИМОСТИ  (нужны на каждой Linux-машине с приложением)         │
│                                                                              │
│  Debian / Ubuntu:                                                            │
│    sudo apt install xclip python3-tk python3-gi                              │
│    sudo apt install gir1.2-ayatana-appindicator3-0.1                        │
│                                                                              │
│  Fedora / RHEL:                                                              │
│    sudo dnf install xclip python3-tkinter python3-gobject                   │
│    sudo dnf install libayatana-appindicator-gtk3                             │
│                                                                              │
│  Arch Linux:                                                                 │
│    sudo pacman -S xclip tk python-gobject libayatana-appindicator            │
│                                                                              │
│  xclip        — буфер обмена (pyperclip)                                    │
│  python3-tk   — Tkinter / customtkinter GUI                                  │
│  python3-gi   — PyGObject (pystray: иконка в трее)                           │
│  appindicator — трей-индикатор в GNOME / KDE / XFCE                         │
└──────────────────────────────────────────────────────────────────────────────┘"""


def read_app_version(script_dir: str) -> str:
    """Читает APP_VERSION из src/jh_version.py без импорта модуля."""
    fallback = "1.2.0"
    version_file = os.path.join(script_dir, "src", "jh_version.py")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'APP_VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+)*)["\']', content)
        if match:
            return match.group(1)
    except Exception as exc:
        print(f"[Версия]: Не удалось прочитать jh_version.py ({exc}). Используем {fallback}.")
    return fallback


def build() -> None:
    if sys.platform == "win32":
        print(
            "[Ошибка]: build_linux.py предназначен для Linux. "
            "На Windows используйте build_exe.py."
        )
        sys.exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    print(f"[0/4] Рабочая директория: {script_dir}")
    print()
    print(_DEPS_NOTICE)
    print()

    version_str = read_app_version(script_dir)
    app_name = "job-hunter-ai"

    # ── 1. Зависимости сборки ────────────────────────────────────────────────
    print("\n[1/4] Установка зависимостей сборки...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--upgrade",
            "pyinstaller", "customtkinter", "pillow", "plyer",
            "pynput", "pystray", "pyperclip", "pypdf",
        ],
        check=True,
    )

    # ── 2. Пути CustomTkinter ─────────────────────────────────────────────────
    print("\n[2/4] Определение путей CustomTkinter...")
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        ctk_data_arg = f"{ctk_path}{os.path.pathsep}customtkinter"
    except ImportError:
        print("[Ошибка]: customtkinter не найден — pip install customtkinter.")
        return

    main_script = os.path.join("src", "main_app.py")
    if not os.path.exists(main_script):
        print(f"[Ошибка]: Точка входа {main_script!r} не найдена в {script_dir}.")
        return

    # Ассеты: logo.png — иконка приложения и логотип внутри UI.
    # _resolve_asset() в main_app.py ищет файл рядом с бинарником (sys._MEIPASS),
    # поэтому упаковываем его с dest=".".
    logo_file = os.path.join("assets", "logo.png")
    icon_ico  = "icon.ico"   # PyInstaller принимает .ico даже на Linux для --icon

    # ── 3. PyInstaller ───────────────────────────────────────────────────────
    print(f"\n[3/4] Запуск PyInstaller (v{version_str}, target={app_name})...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--noconsole",           # Без консольного окна (GUI-приложение)
        f"--name={app_name}",
        f"--add-data={ctk_data_arg}",
        "--paths=src",

        # pynput: PyInstaller не обнаруживает X11-бэкенды автоматически.
        # --collect-submodules собирает весь пакет; явные --hidden-import нужны
        # для самых глубоких нод, которые collect-submodules может пропустить.
        "--collect-submodules=pynput",
        "--hidden-import=pynput.keyboard",
        "--hidden-import=pynput.mouse",
        "--hidden-import=pynput._util.xorg",
        "--hidden-import=pynput.keyboard._xorg",
        "--hidden-import=pynput.mouse._xorg",

        # pystray: GTK-бэкенд для иконки в трее (GNOME/KDE/XFCE с X11)
        "--hidden-import=pystray",
        "--hidden-import=pystray._gtk",

        "--hidden-import=pyperclip",
    ]

    if os.path.exists(logo_file):
        cmd += [
            f"--icon={logo_file}",
            f"--add-data={logo_file}{os.path.pathsep}.",
        ]
        print(f"-> Логотип/иконка: {logo_file}")
    else:
        print(f"[Предупреждение]: {logo_file} не найден — иконка будет стандартной.")

    # icon.ico тоже упаковываем: _resolve_asset() может запросить его на Windows
    # при запуске из исходников в смешанной среде.
    if os.path.exists(icon_ico):
        cmd.append(f"--add-data={icon_ico}{os.path.pathsep}.")

    cmd.append(main_script)

    print(f"\nКоманда: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("\n" + "=" * 60)
        print("❌  СБОРКА ПРОВАЛИЛАСЬ!")
        print("=" * 60)
        print("STDOUT:")
        print(result.stdout)
        print("\nSTDERR:")
        print(result.stderr)
        print("=" * 60)
        return

    # ── 4. Перенос артефактов ─────────────────────────────────────────────────
    # PyInstaller кладёт результат в dist/{app_name}/{app_name}
    dist_app_dir = os.path.join(script_dir, "dist", app_name)
    src_bin      = os.path.join(dist_app_dir, app_name)
    src_internal = os.path.join(dist_app_dir, "_internal")

    # Целевая папка — рядом с проектом (аналогично build_exe.py),
    # если родительская директория доступна для записи.
    parent_dir = os.path.dirname(script_dir)
    target_dir = os.path.join(parent_dir, "Job Hunter AI Linux")
    if not os.path.isdir(parent_dir) or not os.access(parent_dir, os.W_OK):
        target_dir = os.path.join(script_dir, "dist_output")

    print(f"\n[4/4] Перенос в: {target_dir}...")

    try:
        os.makedirs(target_dir, exist_ok=True)

        dest_bin = os.path.join(target_dir, app_name)
        if os.path.exists(dest_bin):
            os.remove(dest_bin)
        shutil.move(src_bin, dest_bin)
        os.chmod(dest_bin, 0o755)
        print(f"-> Бинарник:   {dest_bin}")

        dest_internal = os.path.join(target_dir, "_internal")
        if os.path.exists(dest_internal):
            shutil.rmtree(dest_internal)
        shutil.move(src_internal, dest_internal)
        print("-> Зависимости: _internal/")

        # Очистка временных папок сборки
        print("\n[Очистка]...")
        shutil.rmtree(os.path.join(script_dir, "build"), ignore_errors=True)
        shutil.rmtree(os.path.join(script_dir, "dist"),  ignore_errors=True)
        spec_file = os.path.join(script_dir, f"{app_name}.spec")
        if os.path.exists(spec_file):
            os.remove(spec_file)

        print("\n" + "=" * 60)
        print(f"  СБОРКА ЗАВЕРШЕНА!  Job Hunter AI v{version_str}")
        print(f"  Запуск: {dest_bin}")
        print("=" * 60)
        print()
        print(_DEPS_NOTICE)

    except Exception as exc:
        print(f"\n[Ошибка переноса]: {exc}")


if __name__ == "__main__":
    build()
