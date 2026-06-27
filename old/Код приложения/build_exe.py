# build_exe.py
import os
import sys
import subprocess
import shutil

def install_and_compile():
    # Автоматическое определение папки, где физически находится этот скрипт build_exe.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Принудительно меняем рабочую директорию процесса на папку проекта
    os.chdir(script_dir)
    print(f"[0/4] Рабочая директория сборщика установлена на: {script_dir}")

    print("[1/4] Проверка и установка необходимых утилит для сборки...")
    # Гарантируем, что PyInstaller установлен
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "customtkinter", "flask", "flask_cors"], check=True)

    print("\n[2/4] Определение путей CustomTkinter...")
    # Для customtkinter нужно явно указать путь к его внутренним файлам (темам, шрифтам)
    try:
        import customtkinter
        ctk_path = os.path.dirname(customtkinter.__file__)
        # Формируем аргумент добавления папки customtkinter в сборку
        # На Windows разделитель путей в PyInstaller - точка с запятой ';'
        ctk_data_arg = f"{ctk_path}{os.path.pathsep}customtkinter"
    except ImportError:
        print("[Ошибка]: Не удалось импортировать customtkinter для сборки.")
        return

    # Имя главного файла в текущей папке проекта
    main_script = "main_app.py"
    icon_file = "icon.ico"

    if not os.path.exists(main_script):
        print(f"[Ошибка]: Главный файл {main_script} не найден в директории проекта ({script_dir})!")
        return

    print("\n[3/4] Запуск компиляции через PyInstaller...")
    
    # Вызываем PyInstaller как модуль текущего интерпретатора Python (sys.executable -m PyInstaller).
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",               # Не спрашивать подтверждение на перезапись папки сборки
        "--onedir",                  # Собираем в одну папку (наиболее стабильный вариант для сложных GUI)
        "--windowed",                # Отключает появление консольного черного окна при запуске
        f"--add-data={ctk_data_arg}", # Вшиваем ассеты customtkinter
    ]

    # Если есть иконка, добавляем её в сборку
    if os.path.exists(icon_file):
        cmd.append(f"--icon={icon_file}")
        # Также копируем иконку внутрь папки сборки, так как results_ui.py и main_app.py ищут её рядом с собой
        cmd.append(f"--add-data={icon_file}{os.path.pathsep}.")
    else:
        print("[Предупреждение]: Файл icon.ico не найден в корне. Сборка будет выполнена со стандартной иконкой.")

    # Добавляем целевой скрипт
    cmd.append(main_script)

    print(f"Выполняется команда: {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[Ошибка]: Сбой во время работы PyInstaller: {e}")
        return

    # Пути к результатам сборки
    dist_app_dir = os.path.join(script_dir, "dist", "main_app")
    src_exe = os.path.join(dist_app_dir, "main_app.exe")
    src_internal = os.path.join(dist_app_dir, "_internal")

    # Автоматически находим соседнюю папку "Job Hunter AI" на Рабочем столе
    parent_dir = os.path.dirname(script_dir)
    target_dir = os.path.join(parent_dir, "Job Hunter AI")
    
    # Если папка сборки инсталлятора не найдена рядом, сохраняем в текущую
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

        # Очистка временного мусора PyInstaller
        print("\n[Очистка]: Удаление временных папок сборки...")
        shutil.rmtree(os.path.join(script_dir, "build"))
        shutil.rmtree(os.path.join(script_dir, "dist"))
        spec_file = os.path.join(script_dir, "main_app.spec")
        if os.path.exists(spec_file):
            os.remove(spec_file)
        
        print("\n==================================================")
        print(" СБОРКА И АВТОПЕРЕНОС УСПЕШНО ЗАВЕРШЕНЫ!")
        print(f" Все файлы подготовлены в папке: {target_dir}")
        print(" Теперь вы можете просто запустить сборку в Inno Setup!")
        print("==================================================")

    except Exception as err:
        print(f"\n[Ошибка автопереноса/очистки]: {err}")

if __name__ == "__main__":
    install_and_compile()