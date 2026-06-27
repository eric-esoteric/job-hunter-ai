# jh_version.py
"""
Единый источник истины о версии приложения Job Hunter AI.

Эту константу импортируют:
  - main_app.py        -> заголовок главного окна и т.п.
  - build_exe.py       -> генерация version_info.txt для PyInstaller (метаданные .exe)

Чтобы выпустить новую версию, достаточно поменять APP_VERSION здесь.
Формат строго "MAJOR.MINOR.PATCH" (три числа), т.к. формат Windows VERSIONINFO
требует ровно четыре числовых компонента (последний — билд, по умолчанию 0).
"""

APP_NAME = "Job Hunter AI"
APP_VERSION = "2.0.2"

# Метаданные для свойств .exe в Windows
COMPANY_NAME = "Job Hunter AI"
FILE_DESCRIPTION = "Job Hunter AI — персональный ассистент по автоматизации карьеры"
INTERNAL_NAME = "JobHunterAI"
ORIGINAL_FILENAME = "Job Hunter AI.exe"
PRODUCT_NAME = "Job Hunter AI"
LEGAL_COPYRIGHT = "© Job Hunter AI"


def get_version_tuple():
    """
    Преобразует строку версии "1.2.0" в кортеж из 4 чисел (1, 2, 0, 0)
    для Windows VERSIONINFO (filevers / prodvers).
    Некорректные/неполные значения безопасно дополняются нулями.
    """
    parts = []
    for chunk in str(APP_VERSION).split("."):
        chunk = chunk.strip()
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def get_window_title():
    """Заголовок главного окна вида 'Job Hunter AI v1.2.0'."""
    return f"{APP_NAME} v{APP_VERSION}"
