# -*- coding: utf-8 -*-
"""
Помощники для работы как из исходников, так и из собранного PyInstaller
exe: определение путей к ресурсам (шаблоны, встроенный Tesseract) и
настройка pytesseract на использование встроенного движка OCR, если он
был упакован внутрь exe (см. build.ps1), либо системного, если он
установлен отдельно.
"""

import os
import platform
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True, если код выполняется из собранного PyInstaller exe."""
    return getattr(sys, "frozen", False)


def resource_path(relative: str) -> Path:
    """Путь к упакованному внутрь exe ресурсу (только для чтения):
    шаблоны, tesseract_bin. В режиме разработки — просто путь рядом со
    скриптом."""
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base / relative


def app_base_dir() -> Path:
    """Папка, где лежат/должны создаваться пользовательские файлы
    (input.txt, gui_settings.json, debug/). Для собранного exe — папка
    рядом с exe (не временная папка распаковки _MEIPASS), чтобы
    пользователь мог держать входной файл рядом с программой."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BUNDLED_TESSERACT_DIR = resource_path("tesseract_bin")
BUNDLED_TESSERACT_EXE = BUNDLED_TESSERACT_DIR / "tesseract.exe"
BUNDLED_TESSDATA_DIR = BUNDLED_TESSERACT_DIR / "tessdata"

FALLBACK_TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def resolve_tesseract_cmd(override: str = "") -> str:
    """Определяет, какой tesseract.exe использовать (в порядке
    приоритета): путь, заданный пользователем вручную -> встроенный в
    exe -> системный установленный по умолчанию. Возвращает пустую
    строку, если ничего не найдено."""
    if override and Path(override).exists():
        return override
    if BUNDLED_TESSERACT_EXE.exists():
        return str(BUNDLED_TESSERACT_EXE)
    if platform.system() == "Windows" and Path(FALLBACK_TESSERACT_CMD).exists():
        return FALLBACK_TESSERACT_CMD
    return ""


def configure_tesseract(override: str = ""):
    """Настраивает pytesseract на найденный движок Tesseract. Возвращает
    (ok: bool, message: str, path_used: str)."""
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract не установлен.", ""

    cmd = resolve_tesseract_cmd(override)
    if not cmd:
        return False, (
            "Tesseract-OCR не найден (ни встроенный, ни системный). "
            "OCR-проверка результатов работать не будет."
        ), ""

    pytesseract.pytesseract.tesseract_cmd = cmd

    # Если используется встроенная в exe копия — явно указываем ей, где
    # искать языковые данные (tessdata), т.к. она распакована во
    # временную папку и не имеет системной регистрации.
    if Path(cmd) == BUNDLED_TESSERACT_EXE and BUNDLED_TESSDATA_DIR.exists():
        os.environ["TESSDATA_PREFIX"] = str(BUNDLED_TESSDATA_DIR)

    return True, f"Используется Tesseract: {cmd}", cmd
