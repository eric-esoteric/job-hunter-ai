import os
import sys
import subprocess
import shutil

def run_self_healing_refactor(script_dir):
    """
    Автоматически переименовывает файлы проекта во избежание конфликтов импорта 
    с установленными в системе библиотеками (например, storage_manager) 
    и автоматически обновляет ссылки в коде.
    """
    print("\n[Рефакторинг] Запуск автоматического устранения конфликтов имён (Self-Healing)...")
    src_dir = os.path.join(script_dir, "src")
    if not os.path.exists(src_dir):
        print("[Рефакторинг] Папка src/ не найдена. Пропускаем.")
        return

    # Карта переименования файлов во избежание маскирования системных библиотек
    rename_map = {
        "storage_manager.py": "jh_storage_manager.py",
        "ai_engine.py": "jh_ai_engine.py",
        "results_ui.py": "jh_results_ui.py"
    }

    # 1. Сначала переносим всё из корня в src, если что-то осталось
    for old_name in rename_map.keys():
        root_file = os.path.join(script_dir, old_name)
        if os.path.exists(root_file):
            dest = os.path.join(src_dir, old_name)
            if not os.path.exists(dest):
                print(f"-> Переносим {old_name} из корня в src/...")
                shutil.move(root_file, dest)
            else:
                print(f"-> Удаляем дубликат {old_name} из корня...")
                os.remove(root_file)

    # Переносим также main_app.py из корня в src/, если он там залежался
    root_main = os.path.join(script_dir, "main_app.py")
    if os.path.exists(root_main):
        dest_main = os.path.join(src_dir, "main_app.py")
        if not os.path.exists(dest_main):
            print("-> Переносим main_app.py из корня в src/...")
            shutil.move(root_main, dest_main)
        else:
            print("-> Удаляем дубликат main_app.py из корня...")
            os.remove(root_main)

    # Переносим также jh_version.py (единый источник версии) из корня в src/, если он там.
    root_version = os.path.join(script_dir, "jh_version.py")
    if os.path.exists(root_version):
        dest_version = os.path.join(src_dir, "jh_version.py")
        if not os.path.exists(dest_version):
            print("-> Переносим jh_version.py из корня в src/...")
            shutil.move(root_version, dest_version)
        else:
            print("-> Удаляем дубликат jh_version.py из корня...")
            os.remove(root_version)

    # 2. Переименовываем файлы внутри src/ в уникальные имена jh_*
    for old_name, new_name in rename_map.items():
        old_path = os.path.join(src_dir, old_name)
        new_path = os.path.join(src_dir, new_name)
        if os.path.exists(old_path):
            if os.path.exists(new_path):
                print(f"-> Найдена старая копия {old_name}. Удаляем её, так как jh_ версия уже существует.")
                os.remove(old_path)
            else:
                print(f"-> Уникализируем имя: {old_name} -> {new_name}")
                os.rename(old_path, new_path)

    # 3. Автоматически правим импорты во всех файлах внутри src/
    print("[Рефакторинг] Автоматическое обновление импортов и вызовов функций в кодовой базе...")
    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        code = f.read()

                    # Правим импорты и обращения к модулям
                    modified = False
                    
                    # Заменяем storage_manager
                    if "storage_manager" in code and "jh_storage_manager" not in code:
                        code = code.replace("import storage_manager", "import jh_storage_manager")
                        code = code.replace("storage_manager.", "jh_storage_manager.")
                        modified = True
                        
                    # Заменяем ai_engine
                    if "ai_engine" in code and "jh_ai_engine" not in code:
                        code = code.replace("import ai_engine", "import jh_ai_engine")
                        code = code.replace("ai_engine.", "jh_ai_engine.")
                        modified = True
                        
                    # Заменяем results_ui
                    if "results_ui" in code and "jh_results_ui" not in code:
                        code = code.replace("import results_ui", "import jh_results_ui")
                        code = code.replace("results_ui.", "jh_results_ui.")
                        modified = True

                    if modified:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(code)
                        print(f"   ✓ Успешно обновлены импорты в файле: {file}")
                except Exception as e:
                    print(f"   [Ошибка рефакторинга] Не удалось обновить {file}: {e}")

def read_app_version(script_dir):
    """
    Читает версию приложения из единого источника истины src/jh_version.py,
    не импортируя весь модуль (чтобы не тянуть зависимости GUI при сборке).
    Возвращает кортеж (version_string, (a, b, c, d)).
    При любой ошибке безопасно откатывается на 1.2.0.
    """
    fallback_str = "1.2.0"
    version_file = os.path.join(script_dir, "src", "jh_version.py")
    version_str = fallback_str
    try:
        import re
        with open(version_file, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.search(r'APP_VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+)*)["\']', content)
        if match:
            version_str = match.group(1)
    except Exception as e:
        print(f"[Версия]: Не удалось прочитать jh_version.py ({e}). Используем {fallback_str}.")

    parts = []
    for chunk in version_str.split("."):
        chunk = chunk.strip()
        parts.append(int(chunk) if chunk.isdigit() else 0)
    while len(parts) < 4:
        parts.append(0)
    return version_str, tuple(parts[:4])


def generate_version_file(script_dir):
    """
    Генерирует Windows VERSIONINFO-файл (version_info.txt) для PyInstaller.
    Этот файл через аргумент --version-file запекает официальную версию прямо
    в метаданные .exe: пользователь увидит её в Свойства -> Подробно, а также
    она попадёт в строку версии деинсталлятора Windows.
    Возвращает путь к созданному файлу или None при ошибке.
    """
    version_str, v = read_app_version(script_dir)
    out_path = os.path.join(script_dir, "version_info.txt")

    content = f"""# UTF-8
# Автогенерируемый файл версии. Не редактировать вручную —
# источник истины: src/jh_version.py (константа APP_VERSION).
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v[0]}, {v[1]}, {v[2]}, {v[3]}),
    prodvers=({v[0]}, {v[1]}, {v[2]}, {v[3]}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
woudl_placeholder
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1049, 1200])])
  ]
)
"""
    # Собираем StringTable аккуратно (без проблемных f-string вложений).
    string_table = (
        "        StringTable(\n"
        "          u'041904b0',\n"
        "          [\n"
        "            StringStruct(u'CompanyName', u'Job Hunter AI'),\n"
        "            StringStruct(u'FileDescription', u'Job Hunter AI - ассистент по автоматизации карьеры'),\n"
        f"            StringStruct(u'FileVersion', u'{version_str}'),\n"
        "            StringStruct(u'InternalName', u'JobHunterAI'),\n"
        "            StringStruct(u'LegalCopyright', u'(c) Job Hunter AI'),\n"
        "            StringStruct(u'OriginalFilename', u'Job Hunter AI.exe'),\n"
        "            StringStruct(u'ProductName', u'Job Hunter AI'),\n"
        f"            StringStruct(u'ProductVersion', u'{version_str}')\n"
        "          ]\n"
        "        )\n"
    )
    content = content.replace("woudl_placeholder", string_table.rstrip("\n"))

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[Версия]: Сгенерирован version_info.txt с версией {version_str} -> {v}")
        return out_path
    except Exception as e:
        print(f"[Версия]: Не удалось записать version_info.txt: {e}")
        return None


def try_run_inno_setup(script_dir):
    """
    Пытается запустить компилятор Inno Setup (ISCC.exe) для создания установщика.
    Ищет ISCC.exe в системном PATH и в стандартных папках установки Inno Setup.
    Вызывается автоматически после успешной сборки PyInstaller.
    """
    iscc_path = shutil.which("ISCC.exe") or shutil.which("ISCC")
    if not iscc_path:
        for candidate in [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
            r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
            r"C:\Program Files\Inno Setup 5\ISCC.exe",
        ]:
            if os.path.exists(candidate):
                iscc_path = candidate
                break

    if not iscc_path:
        print("\n[Inno Setup]: ISCC.exe не найден в PATH и стандартных папках установки.")
        print("              Установите Inno Setup (https://jrsoftware.org/isinfo.php) или")
        print("              добавьте путь к ISCC.exe в переменную окружения PATH,")
        print("              чтобы установщик собирался автоматически.")
        return

    iss_file = os.path.join(script_dir, "installer.iss")
    if not os.path.exists(iss_file):
        print(f"\n[Inno Setup]: Файл installer.iss не найден в {script_dir}. Пропускаем.")
        return

    print(f"\n[Inno Setup]: Компилятор найден: {iscc_path}")
    print(f"[Inno Setup]: Запуск компиляции установщика из {iss_file}...")
    inno_result = subprocess.run(
        [iscc_path, iss_file],
        capture_output=True,
        text=True,
        cwd=script_dir
    )

    if inno_result.returncode == 0:
        setup_exe = os.path.join(script_dir, "JobHunterAI_Setup.exe")
        print("[Inno Setup]: ✓ Установщик успешно создан!")
        if os.path.exists(setup_exe):
            print(f"              Файл: {setup_exe}")
    else:
        print("[Inno Setup]: ✗ Ошибка при компиляции установщика!")
        if inno_result.stdout:
            print(inno_result.stdout)
        if inno_result.stderr:
            print(inno_result.stderr)


def install_and_compile():
    # Автоматическое определение папки, где физически находится этот скрипт build_exe.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Принудительно меняем рабочую директорию процесса на папку проекта
    os.chdir(script_dir)
    print(f"[0/4] Рабочая директория сборщика установлена на: {script_dir}")

    # Запускаем автоматический рефакторинг перед сборкой
    run_self_healing_refactor(script_dir)

    print("\n[1/4] Проверка и установка необходимых утилит для сборки...")
    # Гарантируем, что PyInstaller установлен
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "customtkinter", "flask", "flask_cors", "pillow"], check=True)

    print("\n[2/4] Определение путей CustomTkinter...")
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        ctk_data_arg = f"{ctk_path}{os.path.pathsep}customtkinter"
    except ImportError:
        print("[Ошибка]: Не удалось импортировать customtkinter для сборки.")
        return

    # Точка входа в структурированной папке src/
    main_script = os.path.join("src", "main_app.py")
    icon_file = "icon.ico"
    logo_file = "logo.png"

    if not os.path.exists(main_script):
        print(f"[Ошибка]: Главный файл {main_script} не найден в директории проекта ({script_dir})!")
        return

    print("\n[3/4] Запуск компиляции через PyInstaller...")

    # Генерируем файл версии Windows для запекания в метаданные .exe.
    version_file_path = generate_version_file(script_dir)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",               # Не спрашивать подтверждение на перезапись
        "--onedir",                  # Собираем в одну папку
        "--windowed",                # Отключает появление консольного черного окна при запуске
        f"--add-data={ctk_data_arg}", # Вшиваем ассеты customtkinter
        "--paths=src",               # Указываем PyInstaller искать локальные импорты в папке src/
    ]

    if os.path.exists(icon_file):
        cmd.append(f"--icon={icon_file}")
        cmd.append(f"--add-data={icon_file}{os.path.pathsep}.")
    else:
        print("[Предупреждение]: Файл icon.ico не найден в корне. Сборка будет выполнена со стандартной иконкой.")

    if os.path.exists(logo_file):
        cmd.append(f"--add-data={logo_file}{os.path.pathsep}.")
    else:
        print("[Предупреждение]: Файл logo.png не найден в корне.")

    # Запекаем версию Windows в метаданные exe (свойства файла / деинсталлятор).
    if version_file_path and os.path.exists(version_file_path):
        cmd.append(f"--version-file={version_file_path}")
    else:
        print("[Предупреждение]: version_info.txt не сгенерирован — версия в свойствах .exe будет отсутствовать.")

    # Добавляем целевой скрипт в сборку
    cmd.append(main_script)

    print(f"Выполняется команда: {' '.join(cmd)}\n")
    
    # Запускаем сборку с захватом вывода, чтобы в случае ошибки детально распечатать traceback
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("\n==================================================")
        print("❌ СБОЙ ВЫПОЛНЕНИЯ PYINSTALLER!")
        print("==================================================")
        print("STDOUT (Стандартный вывод):")
        print(result.stdout)
        print("\nSTDERR (Поток ошибок):")
        print(result.stderr)
        print("==================================================")
        return

    # Пути к результатам сборки
    dist_app_dir = os.path.join(script_dir, "dist", "main_app")
    src_exe = os.path.join(dist_app_dir, "main_app.exe")
    src_internal = os.path.join(dist_app_dir, "_internal")

    # Находим целевую папку сборки инсталлятора
    parent_dir = os.path.dirname(script_dir)
    target_dir = os.path.join(parent_dir, "Job Hunter AI")
    
    if not os.path.exists(target_dir):
        target_dir = script_dir

    print(f"\n[4/4] Автоматический перенос файлов в целевую папку: {target_dir}...")
    
    try:
        # 1. Переносим и переименовываем EXE в "Job Hunter AI.exe"
        dest_exe = os.path.join(target_dir, "Job Hunter AI.exe")
        if os.path.exists(dest_exe):
            os.remove(dest_exe)
        shutil.move(src_exe, dest_exe)
        print("-> Файл Job Hunter AI.exe успешно перенесен и переименован.")

        # 2. Переносим папку зависимостей _internal
        dest_internal = os.path.join(target_dir, "_internal")
        if os.path.exists(dest_internal):
            shutil.rmtree(dest_internal)
        shutil.move(src_internal, dest_internal)
        print("-> Системная папка _internal успешно перенесена.")

        print("\n[Очистка]: Удаление временных папок сборки...")
        shutil.rmtree(os.path.join(script_dir, "build"))
        shutil.rmtree(os.path.join(script_dir, "dist"))
        spec_file = os.path.join(script_dir, "main_app.spec")
        if os.path.exists(spec_file):
            os.remove(spec_file)
        # Удаляем временный автогенерируемый файл версии.
        vinfo = os.path.join(script_dir, "version_info.txt")
        if os.path.exists(vinfo):
            os.remove(vinfo)
        
        print("\n==================================================")
        print(" СБОРКА И АВТОПЕРЕНОС УСПЕШНО ЗАВЕРШЕНЫ!")
        print(f" Все файлы подготовлены в папке: {target_dir}")
        print("==================================================")

        # Пробуем автоматически собрать установщик через Inno Setup
        try_run_inno_setup(script_dir)

    except Exception as err:
        print(f"\n[Ошибка автопереноса/очистки]: {err}")

if __name__ == "__main__":
    install_and_compile()