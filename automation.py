# -*- coding: utf-8 -*-
"""
Движок автоматизации: активация окна игры, поиск элементов на экране,
ввод номера паспорта, чтение результатов через OCR и классификация
судимостей на административные / уголовные. Не зависит от GUI —
принимает Settings, функцию логирования и threading.Event для отмены,
чтобы им мог пользоваться и GUI, и (при желании) консоль.
"""

import datetime
import difflib
import hashlib
import platform
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Set

import psutil
import pyautogui

import element_matcher

try:
    import win32con
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

from ocr_setup import configure_tesseract
from settings import (
    BUTTON_IMAGE,
    FACTION_HEADER_IMAGE,
    FIELD_IMAGE,
    INPUT_TEXT,
    MODE_ADMIN,
    MODE_CRIMINAL,
    RESULTS_HEADER_IMAGE,
    Settings,
)

LogFn = Callable[[str], None]

CAT_ADMIN = "admin"
CAT_CRIMINAL = "criminal"


class StopRequested(Exception):
    """Внутренний сигнал прерывания по кнопке 'Стоп' в GUI."""


class AutomationError(Exception):
    """Ошибка, которую нужно показать пользователю и остановить прогон."""


def _noop_log(_msg: str):
    pass


@dataclass
class RunResult:
    total: int = 0
    processed: int = 0
    admin_only: List[str] = field(default_factory=list)
    criminal_only: List[str] = field(default_factory=list)
    both: List[str] = field(default_factory=list)
    skipped: int = 0
    stopped_early: bool = False
    # Статистика времени по записям (заполняется в run(), используется в
    # GUI для итогового уведомления и в логе для сводки "среднее/мин/макс").
    total_time: float = 0.0
    avg_time: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0
    rate_per_min: float = 0.0


# ---------------------------------------------------------------------------
# АКТИВАЦИЯ ОКНА ПО ИМЕНИ ПРОЦЕССА (Windows)
# ---------------------------------------------------------------------------

def _find_hwnd_by_process_name(process_name: str):
    target_pids = {
        proc.info["pid"]
        for proc in psutil.process_iter(["pid", "name"])
        if proc.info["name"] and proc.info["name"].lower() == process_name.lower()
    }
    if not target_pids:
        return None

    found = []

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if not win32gui.GetWindowText(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in target_pids:
            found.append(hwnd)

    win32gui.EnumWindows(enum_handler, None)
    return found[0] if found else None


def list_window_processes():
    """Список имён процессов с видимыми окнами (для выпадающего списка
    выбора игры в GUI) — короче и полезнее, чем весь список процессов
    в системе."""
    if not WIN32_AVAILABLE:
        return []

    names = set()

    def enum_handler(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if not win32gui.GetWindowText(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            names.add(proc.name())
        except Exception:
            pass

    try:
        win32gui.EnumWindows(enum_handler, None)
    except Exception:
        return []

    return sorted(names, key=str.lower)


def find_target_window_rect(process_name: str):
    """(left, top, right, bottom) окна процесса в экранных координатах,
    либо None — используется GUI, чтобы поставить оверлей прогресса
    рядом с окном игры, а не в случайном месте экрана."""
    if not WIN32_AVAILABLE:
        return None
    hwnd = _find_hwnd_by_process_name(process_name)
    if hwnd is None:
        return None
    try:
        return win32gui.GetWindowRect(hwnd)
    except Exception:
        return None


def activate_target_window(process_name: str, log: LogFn = _noop_log, quiet: bool = False) -> bool:
    """Разворачивает и выводит на передний план окно указанного процесса."""
    if not WIN32_AVAILABLE:
        if not quiet:
            log("pywin32 не установлен — активация окна недоступна.")
        return False

    hwnd = _find_hwnd_by_process_name(process_name)
    if hwnd is None:
        if not quiet:
            log(f"Окно процесса '{process_name}' не найдено. Убедитесь, что программа запущена.")
        return False

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.1)
        if not quiet:
            log(f"Окно процесса '{process_name}' активировано.")
        return True
    except Exception as e:
        if not quiet:
            log(f"Не удалось активировать окно '{process_name}': {e}")
        return False


# ---------------------------------------------------------------------------
# ПОДДЕРЖКА НЕСКОЛЬКИХ МОНИТОРОВ (Windows)
# ---------------------------------------------------------------------------

def get_virtual_screen_origin():
    if platform.system() != "Windows":
        return (0, 0)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        return (
            user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        )
    except Exception:
        return (0, 0)


def image_to_screen_coords(x, y, capture_all_monitors: bool):
    if capture_all_monitors:
        origin_x, origin_y = get_virtual_screen_origin()
        return (x + origin_x, y + origin_y)
    return (x, y)


def get_virtual_screen_bounds():
    """(left, top, width, height) всего виртуального рабочего стола —
    используется, чтобы не увести мышь координатами за пределы экрана
    (например, если найденная область оказалась смещена в минус из-за
    промаха в поиске шапки таблицы)."""
    if platform.system() != "Windows":
        try:
            w, h = pyautogui.size()
            return (0, 0, w, h)
        except Exception:
            return (0, 0, 1920, 1080)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        origin_x, origin_y = get_virtual_screen_origin()
        return (
            origin_x,
            origin_y,
            user32.GetSystemMetrics(78),  # SM_CXVIRTUALSCREEN
            user32.GetSystemMetrics(79),  # SM_CYVIRTUALSCREEN
        )
    except Exception:
        return (0, 0, 1920, 1080)


def _is_on_screen(x, y) -> bool:
    left, top, width, height = get_virtual_screen_bounds()
    return left <= x < left + width and top <= y < top + height


def rescue_cursor_from_corner(log: LogFn = _noop_log):
    """pyautogui.failSafeCheck() проверяет ТЕКУЩЕЕ положение курсора
    (не только точку назначения клика/движения) — если курсор хоть раз
    оказался ровно в углу экрана (например, после прерванной попытки
    прокрутки с плохими координатами), он останется там физически, и
    после этого КАЖДЫЙ следующий click/moveTo будет падать с
    FailSafeException, даже если новая цель — не угол. Поэтому перед
    рискованными действиями отодвигаем курсор напрямую через WinAPI
    (в обход pyautogui, чтобы не напороться на тот же fail-safe)."""
    try:
        pos = tuple(pyautogui.position())
    except Exception:
        return
    if pos not in pyautogui.FAILSAFE_POINTS:
        return
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        width, height = pyautogui.size()
        ctypes.windll.user32.SetCursorPos(width // 2, height // 2)
        log("Курсор мыши был в углу экрана (застрял после прошлой ошибки) — отодвинул в центр экрана.")
    except Exception as e:
        log(f"Не удалось отодвинуть курсор от угла экрана: {e}")


def enable_multi_monitor_screenshot(log: LogFn = _noop_log):
    if platform.system() != "Windows":
        log("Захват всех мониторов поддержан только на Windows — пропускаю.")
        return
    try:
        from PIL import ImageGrab
        import pyscreeze

        def _screenshot_all_monitors(imageFilename=None, region=None):
            im = ImageGrab.grab(all_screens=True)
            if region is not None:
                left, top, width, height = region
                im = im.crop((left, top, left + width, top + height))
            if imageFilename is not None:
                im.save(imageFilename)
            return im

        pyscreeze._screenshot_win32 = _screenshot_all_monitors
        pyscreeze.screenshot = _screenshot_all_monitors
        pyautogui.screenshot = _screenshot_all_monitors
        log("Захват всех мониторов включён (поиск будет идти по обоим экранам).")
    except Exception as e:
        log(f"Не удалось включить захват всех мониторов: {e}")
        log("Поиск будет ограничен основным (Primary) монитором.")


# ---------------------------------------------------------------------------
# ПОИСК ЭЛЕМЕНТОВ НА ЭКРАНЕ
# ---------------------------------------------------------------------------

def _save_match_debug(label: str, screenshot, box, score: float, matched: bool, log: LogFn = _noop_log):
    """Сохраняет в debug/ скриншот с отмеченной красным рамкой областью,
    которую нашёл матчер (даже если оценка ниже порога) — чтобы можно
    было ГЛАЗАМИ увидеть, что именно было принято за элемент, вместо
    гадания по одним координатам в логе."""
    try:
        from PIL import ImageDraw

        from ocr_setup import app_base_dir
        debug_dir = app_base_dir() / "debug"
        debug_dir.mkdir(exist_ok=True)

        annotated = screenshot.convert("RGB").copy()
        if box is not None:
            draw = ImageDraw.Draw(annotated)
            draw.rectangle(
                [box.left, box.top, box.left + box.width, box.top + box.height],
                outline=(255, 0, 0),
                width=4,
            )
        status = "found" if matched else "NOTFOUND"
        annotated.save(debug_dir / f"{label}_{status}_score{score:.2f}_full.png")

        if box is not None:
            pad = 200
            left = max(0, box.left - pad)
            top = max(0, box.top - pad)
            right = min(annotated.width, box.left + box.width + pad)
            bottom = min(annotated.height, box.top + box.height + pad)
            annotated.crop((left, top, right, bottom)).save(
                debug_dir / f"{label}_{status}_score{score:.2f}_crop.png"
            )
    except Exception as e:
        log(f"Не удалось сохранить отладочное изображение ({label}): {e}")


def find_element(
    image_path: Path, confidence: float, capture_all_monitors: bool,
    log: LogFn = _noop_log, debug_label: str = "", save_debug: bool = False,
):
    try:
        screenshot = pyautogui.screenshot()
        matched, score, box = element_matcher.find_best(image_path, screenshot, confidence)

        if save_debug:
            _save_match_debug(debug_label or image_path.stem, screenshot, box, score, matched, log)

        if not matched:
            log(
                f"   {image_path.name}: не найдено (лучшее совпадение {score:.2f} "
                f"из требуемых {confidence:.2f}). Если совпадение близко к порогу — "
                "снизьте 'Точность распознавания' на вкладке 'Настройки'. Если "
                "совпадение низкое (<0.3) — экран/разрешение/тема сильно отличаются "
                "от эталонного скриншота, шаблон в templates/ нужно переснять заново."
            )
            return None
        log(f"   {image_path.name}: оценка совпадения {score:.2f} (порог {confidence:.2f}), позиция в кадре ({box.left}, {box.top})")
        x, y = box.left + box.width // 2, box.top + box.height // 2
        return image_to_screen_coords(x, y, capture_all_monitors)
    except Exception as e:
        log(f"Ошибка при поиске {image_path.name}: {e}")
        return None


def locate_ui_elements(settings: Settings, log: LogFn = _noop_log):
    """Находит поле ввода и кнопку поиска на экране. Бросает
    AutomationError, если не удалось найти."""
    log("Ищу поле 'Номер паспорта' на экране...")
    field_pos = find_element(
        FIELD_IMAGE, settings.confidence, settings.capture_all_monitors, log,
        debug_label="field", save_debug=settings.debug_save_ocr_images,
    )
    if field_pos is None:
        raise AutomationError(
            "Поле 'Номер паспорта' не найдено на экране. Проверьте, что "
            "нужное окно видно, либо снизьте 'Точность распознавания' в "
            "дополнительных настройках."
        )
    log(f"Поле найдено: {field_pos}")

    log("Ищу кнопку 'Поиск' на экране...")
    button_pos = find_element(
        BUTTON_IMAGE, settings.confidence, settings.capture_all_monitors, log,
        debug_label="button", save_debug=settings.debug_save_ocr_images,
    )
    if button_pos is None:
        raise AutomationError("Кнопка 'Поиск' не найдена на экране.")
    log(f"Кнопка найдена: {button_pos}")

    if settings.debug_save_ocr_images:
        log(f"Отладочные скриншоты поиска поля/кнопки сохранены в {app_base_dir_debug_hint()}")

    return field_pos, button_pos


def app_base_dir_debug_hint() -> str:
    from ocr_setup import app_base_dir
    return str(app_base_dir() / "debug")


# ---------------------------------------------------------------------------
# ОБЛАСТЬ РЕЗУЛЬТАТОВ И OCR
# ---------------------------------------------------------------------------

def locate_results_header_box(settings: Settings, log: LogFn = _noop_log):
    """Находит шапку таблицы результатов ('Место отбывания наказания') на
    экране. Возвращает element_matcher.Box или None — используется и для
    области результатов (locate_results_panel), и для области 'Паспорт #N'
    (read_passport_number), т.к. обе заданы смещением от этой же шапки."""
    try:
        screenshot = pyautogui.screenshot()
        matched, score, match_box = element_matcher.find_best(RESULTS_HEADER_IMAGE, screenshot, settings.confidence)

        if settings.debug_save_ocr_images:
            _save_match_debug("header", screenshot, match_box, score, matched, log)

        if not matched:
            log(f"   Шапка таблицы результатов не найдена (лучшее совпадение {score:.2f} из {settings.confidence:.2f}).")
            return None
        return match_box
    except Exception as e:
        log(f"Ошибка при поиске шапки таблицы результатов: {e}")
        return None


def results_panel_region(box, settings: Settings):
    return (
        box.left + settings.results_panel_left_offset,
        box.top + settings.results_panel_top_offset,
        settings.results_panel_width,
        settings.results_panel_height,
    )


PASSPORT_NUMBER_RE = re.compile(r"#\s*(\d+)")


def read_passport_number(box, settings: Settings, log: LogFn = _noop_log) -> Optional[str]:
    """Читает номер паспорта из текста 'Паспорт #N' над таблицей
    результатов — нужен только для записей, найденных по имени (см.
    is_name_search), чтобы дописать номер к результату."""
    region = (
        box.left + settings.passport_number_left_offset,
        box.top + settings.passport_number_top_offset,
        settings.passport_number_width,
        settings.passport_number_height,
    )
    image = capture_results_image(region, log)
    if image is None:
        return None
    text = ocr_text(image, log, lang="eng+rus")
    match = PASSPORT_NUMBER_RE.search(text)
    if not match:
        log(f"   Не удалось прочитать номер паспорта из текста: {text!r}")
        return None
    return match.group(1)


def capture_results_image(region, log: LogFn = _noop_log):
    try:
        return pyautogui.screenshot(region=region)
    except Exception as e:
        log(f"Ошибка при захвате области результатов: {e}")
        return None


def ocr_text(image, log: LogFn = _noop_log, lang: str = "rus") -> str:
    if not PYTESSERACT_AVAILABLE:
        return ""
    try:
        return pytesseract.image_to_string(image, lang=lang)
    except Exception as e:
        log(f"Ошибка OCR: {e}")
        return ""


def categorize_text(text: str, settings: Settings) -> Set[str]:
    """Возвращает набор категорий ({'admin', 'criminal'}), чьи ключевые
    слова встретились в переданном OCR-тексте."""
    normalized = text.lower()
    found = set()
    if any(kw in normalized for kw in settings.admin_keywords):
        found.add(CAT_ADMIN)
    if any(kw in normalized for kw in settings.criminal_keywords):
        found.add(CAT_CRIMINAL)
    return found


def image_hash(image) -> str:
    return hashlib.md5(image.tobytes()).hexdigest()


def save_debug(entry_idx, attempt, image, text, log: LogFn = _noop_log):
    from ocr_setup import app_base_dir
    debug_dir = app_base_dir() / "debug"
    debug_dir.mkdir(exist_ok=True)
    image.save(debug_dir / f"entry{entry_idx:03d}_attempt{attempt:02d}.png")
    (debug_dir / f"entry{entry_idx:03d}_attempt{attempt:02d}.txt").write_text(text, encoding="utf-8")


def _wanted_categories(mode: str) -> Set[str]:
    if mode == MODE_ADMIN:
        return {CAT_ADMIN}
    if mode == MODE_CRIMINAL:
        return {CAT_CRIMINAL}
    return {CAT_ADMIN, CAT_CRIMINAL}


def scan_results_for_categories(
    region,
    settings: Settings,
    mode: str,
    entry_idx: int,
    log: LogFn = _noop_log,
    stop_event=None,
) -> Set[str]:
    """Читает видимую область результатов, при необходимости прокручивает
    список вниз, накапливая найденные категории судимостей. Останавливается
    досрочно, как только найдены все категории, требуемые режимом (для
    режима 'both' это обе категории — нужно долистать список полностью,
    если встретилась только одна из них)."""
    wanted = _wanted_categories(mode)
    found: Set[str] = set()
    previous_hash = None
    scroll_x, scroll_y = image_to_screen_coords(
        region[0] + region[2] // 2, region[1] + region[3] // 2, settings.capture_all_monitors
    )
    can_scroll = _is_on_screen(scroll_x, scroll_y)
    if not can_scroll:
        log(
            f"   ВНИМАНИЕ: центр области результатов ({scroll_x}, {scroll_y}) вне экрана — "
            "прокрутка отключена для этой записи, проверяется только видимая часть. "
            "Похоже, область результатов откалибрована неверно для вашего экрана "
            "(см. вкладку 'Настройки' -> смещения области результатов)."
        )

    for attempt in range(settings.max_scroll_attempts + 1):
        if stop_event is not None and stop_event.is_set():
            raise StopRequested()

        image = capture_results_image(region, log)
        if image is None:
            return found

        text = ocr_text(image, log)
        if settings.debug_save_ocr_images:
            save_debug(entry_idx, attempt, image, text, log)

        found |= categorize_text(text, settings)
        if wanted <= found:
            return found

        current_hash = image_hash(image)
        if previous_hash is not None and current_hash == previous_hash:
            break  # содержимое не изменилось после прокрутки — список закончился
        previous_hash = current_hash

        if not can_scroll:
            break

        if attempt < settings.max_scroll_attempts:
            rescue_cursor_from_corner(log)
            pyautogui.moveTo(scroll_x, scroll_y)
            pyautogui.scroll(settings.scroll_amount, x=scroll_x, y=scroll_y)
            time.sleep(settings.scroll_delay)

    return found


# ---------------------------------------------------------------------------
# ВКЛАДКА "ФРАКЦИЯ" — парсинг списка участников (столбцы "Имя" и
# "Последний вход") и отбор кандидатов на исключение по неактиву.
# Исключение из фракции программа НЕ выполняет — только собирает список
# кандидатов, решение и сам клик по кнопке исключения остаются за
# пользователем.
# ---------------------------------------------------------------------------

# Разделители в дате, как их может увидеть OCR ("/" иногда распознаётся как
# "." или ","), плюс произвольное количество "мусорных" символов между датой
# и временем (OCR иногда путает пробел с другими символами).
FACTION_DATE_RE = re.compile(
    r"(\d{1,2})[./,](\d{1,2})[./,](\d{4}).{0,3}?(\d{1,2}):(\d{2})"
)
# Игровой ник — это "Слово Слово" (Имя Фамилия), каждое слово из букв
# (кириллица или латиница, могут быть "-"/"'"). Строки, не подходящие под
# этот вид (символьный мусор вида "©OD.diD Oe", одиночные буквы вида
# "ИА ОО" — обычно OCR-артефакты от аватарки/иконок), отбрасываются.
FACTION_NAME_RE = re.compile(
    r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'-]{2,}(?:\s+[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё'-]{1,})+$"
)

# Порог схожести строк (0..1, см. difflib.SequenceMatcher.ratio), при
# котором два прочитанных через OCR имени считаются одним и тем же
# участником, повторно прочитанным на разных прокрутках (сама прокрутка
# списком, как правило, идёт с перехлёстом, и OCR не всегда распознаёт
# одну и ту же строку одинаково от захвата к захвату).
FACTION_NAME_DUPLICATE_RATIO = 0.84
# Если у двух записей СОВПАДАЕТ распознанная дата "Последний вход"
# минута-в-минуту И совпадает ПЕРВОЕ слово (имя) — считаем это одним и тем
# же участником, даже если второе слово (фамилия) прочиталось совсем
# по-разному (OCR иногда сильно портит именно "хвост" строки). Требование
# по первому слову важно: во фракции часто у многих общая "фамилия" (вида
# "Aether"), и такие РАЗНЫЕ люди иногда заходят в игру в одну и ту же
# минуту — по одной дате входа их различать нельзя, а вот по первому слову
# (которое OCR почти не портит) можно.
FACTION_FIRST_WORD_SAME_LOGIN_RATIO = 0.8


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _first_word(name: str) -> str:
    return name.split(" ", 1)[0]


def _is_same_member(name: str, login_dt, other_name: str, other_login_dt) -> bool:
    """Считает ли пару (имя, дата входа) записями ОДНОГО И ТОГО ЖЕ
    участника — либо по схожести самого имени, либо (при точном совпадении
    минуты входа) по схожести только первого слова (имени, без фамилии).
    Общая логика для дедупликации как во время сканирования (см.
    collect_faction_members), так и постфактум (dedup_fuzzy_members)."""
    if name == other_name:
        return True
    if _name_similarity(name, other_name) >= FACTION_NAME_DUPLICATE_RATIO:
        return True
    if login_dt is not None and other_login_dt is not None and login_dt == other_login_dt:
        if _name_similarity(_first_word(name), _first_word(other_name)) >= FACTION_FIRST_WORD_SAME_LOGIN_RATIO:
            return True
    return False


def _find_matching_member(members: List[dict], name: str, login_dt) -> Optional[dict]:
    for m in members:
        if _is_same_member(name, login_dt, m["name"], m["last_login"]):
            return m
    return None


def dedup_fuzzy_members(members: List[dict]) -> List[dict]:
    """Схлопывает повторные прочтения одного и того же участника (тот же
    человек, прочитанный OCR несколько раз на перехлёстывающихся прокрутках
    списка, иногда с небольшими различиями в написании) в одну запись.
    Подстраховка на случай, если что-то не схлопнулось "на лету" во время
    самого сканирования (см. collect_faction_members) — например, если
    похожая запись появилась в списке позже той, с которой могла бы
    совпасть."""
    result: List[dict] = []
    for m in members:
        match = _find_matching_member(result, m["name"], m["last_login"])
        if match is None:
            result.append(dict(m))
        elif match["last_login"] is None and m["last_login"] is not None:
            match["last_login"] = m["last_login"]
            match["last_login_raw"] = m["last_login_raw"]
    return result


def parse_faction_login(text: str) -> Optional[datetime.datetime]:
    """Разбирает дату/время последнего входа из OCR-текста вида
    '16/07/2026 01:17'. Возвращает None, если строка не распознана как
    дата (например, OCR не смог прочитать колонку для этой строки)."""
    match = FACTION_DATE_RE.search(text)
    if not match:
        return None
    day, month, year, hour, minute = (int(g) for g in match.groups())
    try:
        return datetime.datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def locate_faction_header(settings: Settings, log: LogFn = _noop_log):
    """Находит шапку таблицы участников фракции ('Имя', 'Последний вход'...)
    на экране. Возвращает element_matcher.Box или None."""
    try:
        screenshot = pyautogui.screenshot()
        matched, score, box = element_matcher.find_best(FACTION_HEADER_IMAGE, screenshot, settings.confidence)

        if settings.debug_save_ocr_images:
            _save_match_debug("faction_header", screenshot, box, score, matched, log)

        if not matched:
            log(
                f"   Шапка таблицы участников не найдена (лучшее совпадение {score:.2f} "
                f"из требуемых {settings.confidence:.2f})."
            )
            return None
        log(f"   Шапка найдена: оценка совпадения {score:.2f}, позиция ({box.left}, {box.top}).")
        return box
    except Exception as e:
        log(f"Ошибка при поиске шапки таблицы участников: {e}")
        return None


def faction_column_regions(box, settings: Settings):
    """Возвращает (name_region, login_region) — области столбцов 'Имя' и
    'Последний вход' как смещения от найденной шапки таблицы."""
    top = box.top + box.height + settings.faction_panel_top_offset
    name_region = (
        box.left + settings.faction_name_col_left_offset,
        top,
        settings.faction_name_col_width,
        settings.faction_panel_height,
    )
    login_region = (
        box.left + settings.faction_login_col_left_offset,
        top,
        settings.faction_login_col_width,
        settings.faction_panel_height,
    )
    return name_region, login_region


FACTION_TOTAL_RE = re.compile(r"(\d+)")


def faction_total_region(box, settings: Settings):
    """Область текста 'Участников: N' — выше шапки таблицы колонок, отсюда
    отрицательный top-offset."""
    return (
        box.left + settings.faction_total_left_offset,
        box.top + settings.faction_total_top_offset,
        settings.faction_total_width,
        settings.faction_total_height,
    )


def read_faction_total_count(box, settings: Settings, log: LogFn = _noop_log) -> Optional[int]:
    """Читает заявленное общее число участников из текста 'Участников: N'
    вверху страницы (см. faction_total_region). Возвращает None, если
    прочитать не удалось — вызывающий код в этом случае просто не сможет
    сверить итог с заявленным числом (не фатально)."""
    region = faction_total_region(box, settings)
    image = capture_results_image(region, log)
    if image is None:
        return None
    text = ocr_text(image, log, lang="eng+rus")
    match = FACTION_TOTAL_RE.search(text)
    if not match:
        log(f"   Не удалось прочитать заявленное число участников из текста: {text!r}")
        return None
    return int(match.group(1))


def ocr_column_lines(region, log: LogFn = _noop_log):
    """Захватывает область и распознаёт текст построчно (каждая строка
    таблицы — своя строка текста). Возвращает (lines, image); image нужен
    вызывающему коду отдельно для хэша (детект конца списка) и отладки.

    lang='eng+rus' (а не только 'rus', как для проверки судимостей) —
    игровые никнеймы в GTA5RP обычно набраны латиницей, и с чистым 'rus'
    tesseract подменяет похожие латинские буквы на кириллические
    (например 'Wilson Aether' читается как '\\М!зоп Аепег')."""
    image = capture_results_image(region, log)
    if image is None:
        return [], None
    text = ocr_text(image, log, lang="eng+rus")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines, image


@dataclass
class FactionCollectResult:
    members: List[dict] = field(default_factory=list)
    stopped_early: bool = False
    expected_total: Optional[int] = None


def collect_faction_members(
    settings: Settings,
    log: LogFn = _noop_log,
    stop_event=None,
    count_cb: Optional[Callable[[int, int], None]] = None,
) -> FactionCollectResult:
    """Прокручивает список участников фракции, читая столбцы 'Имя' и
    'Последний вход' через OCR, и собирает уникальных участников (по
    имени). Возвращает FactionCollectResult со списком словарей {"name",
    "last_login_raw", "last_login"} (last_login — datetime или None, если
    дату не удалось распознать). count_cb(collected, attempt) зовётся
    после каждой прочитанной "страницы" списка — для прогресса в GUI.

    Если удалось прочитать заявленное число участников ('Участников: N'
    вверху страницы) и после обычного прохода вниз собрано МЕНЬШЕ — список
    прокручивается обратно наверх и сканируется заново (до
    faction_extra_passes раз), пока не наберётся заявленное число или
    очередной проход не перестанет находить новых людей (тогда это,
    видимо, предел того, что вообще можно прочитать)."""
    rescue_cursor_from_corner(log)

    if settings.capture_all_monitors:
        enable_multi_monitor_screenshot(log)

    ok, message, _ = configure_tesseract(settings.tesseract_cmd_override)
    log(message)
    if not ok:
        log("ВНИМАНИЕ: без OCR парсинг списка участников работать не будет.")

    log(f"Активирую окно процесса '{settings.target_process_name}'...")
    if not activate_target_window(settings.target_process_name, log):
        log("Продолжаю без активации окна. Убедитесь, что список участников фракции открыт и виден на экране.")
    time.sleep(settings.activation_delay)

    log("Ищу шапку таблицы участников на экране...")
    box = locate_faction_header(settings, log)
    if box is None:
        raise AutomationError(
            "Шапка таблицы участников ('Имя', 'Последний вход'...) не найдена на экране. "
            "Откройте список участников фракции и убедитесь, что видны заголовки колонок, "
            "либо откалибруйте область таблицы участников на вкладке 'Настройки'."
        )
    name_region, login_region = faction_column_regions(box, settings)

    expected_total = read_faction_total_count(box, settings, log)
    if expected_total is not None:
        log(f"Заявлено участников на странице: {expected_total}.")
    else:
        log(
            "Не удалось прочитать заявленное число участников ('Участников: N') — "
            "повторные проходы наверх для добора списка будут пропущены."
        )

    members: List[dict] = []
    exact_index: "dict[str, dict]" = {}
    scroll_x, scroll_y = image_to_screen_coords(
        name_region[0] + name_region[2] // 2 + settings.faction_scroll_cursor_x_offset,
        name_region[1] + name_region[3] // 2,
        settings.capture_all_monitors,
    )
    can_scroll = _is_on_screen(scroll_x, scroll_y)
    if not can_scroll:
        log(
            f"   ВНИМАНИЕ: точка прокрутки списка ({scroll_x}, {scroll_y}) вне экрана — прокрутка "
            "отключена, будет прочитана только видимая часть списка. Проверьте калибровку области "
            "таблицы участников на вкладке 'Настройки'."
        )

    def scroll_up_to_top():
        """Спамит прокрутку вверх большим количеством 'кликов', чтобы
        наверняка вернуться к самому началу списка независимо от того, как
        далеко вниз мы уже прокрутились — точный расчёт не нужен, т.к.
        дальше список просто читается заново с начала."""
        rescue_cursor_from_corner(log)
        pyautogui.moveTo(scroll_x, scroll_y)
        up_amount = abs(settings.faction_scroll_amount) * 5
        for _ in range(30):
            pyautogui.scroll(up_amount, x=scroll_x, y=scroll_y)
            time.sleep(settings.faction_scroll_delay)

    def scan_pass(pass_label: str):
        """Один проход вниз от текущей позиции списка. Пополняет общие
        members/exact_index (дедуп общий на все проходы — повторно
        прочитанные уже известные участники просто не добавляются
        повторно). Возвращает True, если проход прерван по стоп-сигналу
        пользователя (StopRequested уже проброшен выше)."""
        no_new_streak = 0
        previous_hash = None
        total_attempts = settings.faction_max_scroll_attempts + 1
        for attempt in range(total_attempts):
            if stop_event is not None and stop_event.is_set():
                raise StopRequested()

            name_lines, name_image = ocr_column_lines(name_region, log)
            login_lines, _ = ocr_column_lines(login_region, log)

            if settings.debug_save_ocr_images and name_image is not None:
                save_debug(attempt, 0, name_image, "\n".join(name_lines), log)

            new_count = 0
            for idx, name in enumerate(name_lines):
                if not FACTION_NAME_RE.search(name):
                    continue
                login_raw = login_lines[idx] if idx < len(login_lines) else ""
                login_dt = parse_faction_login(login_raw)

                # Быстрый путь — точное совпадение строки (частый случай,
                # когда OCR на соседних прокрутках прочитал одинаково).
                existing = exact_index.get(name)
                if existing is None:
                    # Медленный путь — нечёткое совпадение (см.
                    # _is_same_member): тот же человек мог быть прочитан
                    # на другой прокрутке чуть иначе.
                    existing = _find_matching_member(members, name, login_dt)

                if existing is None:
                    record = {"name": name, "last_login_raw": login_raw, "last_login": login_dt}
                    members.append(record)
                    exact_index[name] = record
                    new_count += 1
                else:
                    exact_index.setdefault(name, existing)
                    if login_dt is not None and existing["last_login"] is None:
                        existing["last_login_raw"] = login_raw
                        existing["last_login"] = login_dt

            no_new_streak = 0 if new_count > 0 else no_new_streak + 1

            log(
                f"[{pass_label}, попытка {attempt + 1}/{total_attempts}] строк распознано: {len(name_lines)}, "
                f"новых участников: {new_count}, всего собрано: {len(members)}"
            )
            if count_cb is not None:
                count_cb(len(members), attempt + 1)

            if name_image is None:
                return

            current_hash = image_hash(name_image)
            image_unchanged = previous_hash is not None and current_hash == previous_hash

            if image_unchanged and attempt <= 1:
                # Картинка не изменилась уже после САМОЙ ПЕРВОЙ прокрутки —
                # почти наверняка означает, что прокрутка физически не
                # подействовала на список (не туда наведена мышь / список
                # не в фокусе), а не что список внезапно закончился.
                log(
                    "ПРИЧИНА ОСТАНОВКИ: экран не изменился уже после первой прокрутки. Это "
                    "почти наверняка означает, что прокрутка НЕ сработала (список не в фокусе, "
                    "либо точка прокрутки в настройках наведена не на сам список), а не что "
                    "список из нескольких сотен участников закончился за 1 экран. Проверьте "
                    "'Смещение точки прокрутки вправо' на вкладке 'Настройки' и что список "
                    "виден и активен на экране."
                )
                return

            if image_unchanged:
                log("ПРИЧИНА ОСТАНОВКИ: экран не изменился после прокрутки — дошли до конца списка.")
                return
            previous_hash = current_hash

            if no_new_streak >= settings.faction_stop_after_no_new_streak:
                log(
                    f"ПРИЧИНА ОСТАНОВКИ: {no_new_streak} прокруток подряд без новых участников "
                    "(экран при этом менялся) — похоже, список закончился."
                )
                return

            if not can_scroll or attempt >= settings.faction_max_scroll_attempts:
                log("ПРИЧИНА ОСТАНОВКИ: достигнут предел числа прокруток (страховка от зацикливания).")
                return

            rescue_cursor_from_corner(log)
            pyautogui.moveTo(scroll_x, scroll_y)
            pyautogui.scroll(settings.faction_scroll_amount, x=scroll_x, y=scroll_y)
            time.sleep(settings.faction_scroll_delay)

    result = FactionCollectResult(expected_total=expected_total)
    try:
        scan_pass("основной проход")

        extra_pass = 0
        while (
            can_scroll
            and expected_total is not None
            and len(members) < expected_total
            and extra_pass < settings.faction_extra_passes
        ):
            extra_pass += 1
            log(
                f"Собрано {len(members)} из {expected_total} заявленных — доп. проход {extra_pass}/"
                f"{settings.faction_extra_passes}: прокручиваю список наверх и сканирую заново..."
            )
            scroll_up_to_top()
            before = len(members)
            scan_pass(f"доп. проход {extra_pass}")
            gained = len(members) - before
            log(f"Доп. проход {extra_pass}: найдено новых участников: {gained}.")
            if gained == 0:
                log(
                    "Доп. проход не принёс ничего нового — похоже, это предел того, что можно "
                    "прочитать (неточность в счётчике 'Участников' на странице либо часть записей "
                    "недоступна OCR). Останавливаюсь."
                )
                break
    except StopRequested:
        result.stopped_early = True
        log("\nОстановлено пользователем.")

    deduped = dedup_fuzzy_members(members)
    removed = len(members) - len(deduped)
    log(f"Готово. Прочитано записей: {len(members)}, после схлопывания повторов (перехлёст прокрутки): {len(deduped)}.")
    if removed > 0:
        log(f"   Схлопнуто как повторные прочтения одного и того же участника: {removed}.")
    if expected_total is not None:
        log(f"Заявлено участников: {expected_total}, собрано: {len(deduped)}.")

    unknown_dates = sum(1 for m in deduped if m["last_login"] is None)
    if unknown_dates > 0:
        log(
            f"ВНИМАНИЕ: у {unknown_dates} участников не удалось распознать дату последнего входа "
            "(не попадут в отбор по неактиву — проверьте вручную)."
        )
    result.members = deduped
    return result


def filter_inactive_members(members: List[dict], cutoff: datetime.date) -> List[dict]:
    """Возвращает участников, чей последний вход РАНЬШЕ указанной даты
    (т.е. кандидатов на исключение за неактив). Участники с
    нераспознанной датой в отбор не попадают."""
    cutoff_dt = datetime.datetime.combine(cutoff, datetime.time.min)
    return [m for m in members if m["last_login"] is not None and m["last_login"] < cutoff_dt]


# ---------------------------------------------------------------------------
# ПАРСИНГ ВХОДНОГО ФАЙЛА
# ---------------------------------------------------------------------------

PAREN_RE = re.compile(r"\(([^)]+)\)")
# Строка вида 'Wilson Aether' (без скобок) — Имя и Фамилия, два и более
# слова из букв. Поле "Номер паспорта" в игре также принимает поиск по
# имени в формате 'Имя_Фамилия' (через нижнее подчёркивание), поэтому
# такие строки конвертируются в это значение и вводятся в то же поле.
NAME_ENTRY_RE = re.compile(r"^[A-Za-zА-Яа-яЁё'-]+(?:\s+[A-Za-zА-Яа-яЁё'-]+)+$")


def parse_entries_from_text(text: str, log: LogFn = _noop_log):
    """Парсит текст построчно, независимо от источника (файл или вставленный
    в GUI текст). Поддерживает два формата строк:
    - 'Oper Aether (400560) 7' -> value='400560' (поиск по номеру паспорта);
    - 'Wilson Aether' -> value='Wilson_Aether' (поиск по имени и фамилии —
      вводится в то же поле "Номер паспорта", игра ищет и так, и так)."""
    entries = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = PAREN_RE.search(line)
        if match:
            entries.append({"line": line, "value": match.group(1), "is_name_search": False})
            continue
        if NAME_ENTRY_RE.match(line):
            entries.append({"line": line, "value": "_".join(line.split()), "is_name_search": True})
            continue
        log(f"Пропущена строка (не распознан формат — ни 'Имя (номер)', ни 'Имя Фамилия'): {line}")
    return entries


def parse_entries(filepath: Path, log: LogFn = _noop_log):
    if not filepath.exists():
        raise AutomationError(f"Входной файл не найден: {filepath}")
    return parse_entries_from_text(filepath.read_text(encoding="utf-8"), log)


# ---------------------------------------------------------------------------
# ОСНОВНАЯ ЛОГИКА
# ---------------------------------------------------------------------------

def clear_field(field_pos, settings: Settings):
    pyautogui.click(field_pos)
    time.sleep(settings.action_delay)

    pyautogui.hotkey("ctrl", "a")
    time.sleep(settings.action_delay)
    pyautogui.press("delete")
    time.sleep(settings.action_delay)

    pyautogui.press("end")
    time.sleep(settings.action_delay)
    # interval=0 — без задержки ввода между нажатиями backspace
    pyautogui.press("backspace", presses=settings.clear_field_backspace_count, interval=0)
    time.sleep(settings.action_delay)


def type_entry_value(value: str, settings: Settings, log: LogFn = _noop_log):
    """Вводит значение в уже очищенное и сфокусированное поле.

    Через keyboard.write() — она, в отличие от pyautogui.typewrite(),
    печатает символы через явные unicode-события (а не коды виртуальных
    клавиш, подразумевающие английскую раскладку). Это оказалось причиной
    бага: при активной кириллической раскладке (ЙЦУКЕН) буквы вида
    'Wilson_Aether' терялись при вводе — pyautogui посылал коды клавиш "не
    те" буквы для активной раскладки, — а подчёркивание проходило, потому
    что сидит на клавише, одинаковой в обеих раскладках. Ctrl+V (вставка
    из буфера) здесь тоже не подходит: встроенный в игру браузер на CEF не
    считает синтетическое сочетание клавиш "доверенным" действием и молча
    игнорирует вставку.

    Если модуль 'keyboard' недоступен — откатываемся на посимвольный набор
    через pyautogui (может не сработать при не-английской раскладке)."""
    if KEYBOARD_AVAILABLE:
        keyboard.write(value)
        return
    log(
        "Модуль 'keyboard' не установлен — ввод через pyautogui.typewrite(), "
        "который может терять буквы при не-английской раскладке клавиатуры."
    )
    interval = 0.0 if value.isdigit() else settings.name_entry_type_interval
    pyautogui.typewrite(value, interval=interval)


def process_entry(
    entry, field_pos, button_pos, entry_idx, settings: Settings, mode: str,
    log: LogFn = _noop_log, stop_event=None,
) -> Set[str]:
    """Вводит значение, жмёт 'Поиск', проверяет результат через OCR.
    Возвращает набор найденных категорий судимостей (может быть пустым)."""
    if stop_event is not None and stop_event.is_set():
        raise StopRequested()

    rescue_cursor_from_corner(log)

    if settings.reactivate_each_entry:
        activate_target_window(settings.target_process_name, log, quiet=True)
        time.sleep(settings.activation_delay)

    clear_field(field_pos, settings)

    type_entry_value(entry["value"], settings, log)
    time.sleep(settings.action_delay)

    pyautogui.click(button_pos)
    # Именно одна пауза здесь — между нажатием "Поиск" и анализом результатов
    time.sleep(settings.results_load_delay)

    box = locate_results_header_box(settings, log)
    if box is None:
        log("   Не удалось найти таблицу результатов на экране — запись пропущена.")
        return set()

    if entry.get("is_name_search"):
        passport_number = read_passport_number(box, settings, log)
        if passport_number:
            entry["line"] = f"{entry['line']} ({passport_number})"
            log(f"   Номер паспорта по найденному имени: {passport_number}")
        else:
            log("   Не удалось прочитать номер паспорта для записи, найденной по имени.")

    region = results_panel_region(box, settings)
    return scan_results_for_categories(region, settings, mode, entry_idx, log, stop_event)




def _format_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}ч {minutes}м {secs}с"
    if minutes:
        return f"{minutes}м {secs}с"
    return f"{secs}с"


def run(
    settings: Settings,
    log: LogFn = _noop_log,
    stop_event=None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    result_cb: Optional[Callable[[str, str], None]] = None,
    current_cb: Optional[Callable[[int, int, str], None]] = None,
    stats_cb: Optional[Callable[[dict], None]] = None,
) -> RunResult:
    """Полный прогон автоматизации. Возвращает RunResult со списками
    совпавших строк по категориям. Бросает AutomationError при фатальных
    проблемах (не найдены элементы UI, нет входного файла) и
    StopRequested, если пользователь нажал 'Стоп' (result к этому моменту
    уже содержит всё найденное — вызывающий код сам решает, писать ли
    частичный результат).

    current_cb(idx, total, label) — зовётся ПЕРЕД началом обработки
    записи (для оверлея "кто проверяется сейчас"). stats_cb(dict) —
    зовётся ПОСЛЕ обработки записи с текущей статистикой времени
    (среднее/мин/макс/скорость), которая иначе доступна только постфактум
    в логе."""
    mode = settings.mode
    result = RunResult()
    durations: List[float] = []
    run_start = time.time()

    rescue_cursor_from_corner(log)

    if settings.capture_all_monitors:
        enable_multi_monitor_screenshot(log)

    ok, message, _ = configure_tesseract(settings.tesseract_cmd_override)
    log(message)
    if not ok:
        log("ВНИМАНИЕ: без OCR автоматическая проверка результатов работать не будет.")

    log(f"Активирую окно процесса '{settings.target_process_name}'...")
    if not activate_target_window(settings.target_process_name, log):
        log("Продолжаю без активации окна. Убедитесь, что нужное окно видно на экране.")
    time.sleep(settings.activation_delay)

    field_pos, button_pos = locate_ui_elements(settings, log)

    if settings.input_source == INPUT_TEXT:
        entries = parse_entries_from_text(settings.input_text, log)
    else:
        entries = parse_entries(Path(settings.input_file), log)
    result.total = len(entries)
    log(f"Загружено записей: {result.total}")

    try:
        for idx, entry in enumerate(entries, start=1):
            log(f"[{idx}/{result.total}] {entry['line']}  ->  вводим значение: {entry['value']}")
            if current_cb is not None:
                current_cb(idx, result.total, entry["line"])
            entry_start = time.time()

            try:
                categories = process_entry(entry, field_pos, button_pos, idx, settings, mode, log, stop_event)
            except StopRequested:
                raise
            except Exception as e:
                result.processed = idx
                result.skipped += 1
                durations.append(time.time() - entry_start)
                log(f"   ОШИБКА при обработке записи -> запись пропущена: {e}\n")
                continue

            durations.append(time.time() - entry_start)
            result.processed = idx
            if progress_cb is not None:
                progress_cb(idx, result.total)
            if stats_cb is not None:
                elapsed = time.time() - run_start
                avg = sum(durations) / len(durations)
                stats_cb({
                    "idx": idx,
                    "total": result.total,
                    "label": entry["line"],
                    "duration": durations[-1],
                    "avg": avg,
                    "min": min(durations),
                    "max": max(durations),
                    "elapsed": elapsed,
                    "rate_per_min": (len(durations) / elapsed * 60) if elapsed > 0 else 0.0,
                    "eta_seconds": avg * (result.total - idx),
                })

            if categories == {CAT_ADMIN, CAT_CRIMINAL}:
                result.both.append(entry["line"])
                log("   Найдено: административная И уголовная судимость -> 'УК + АК'\n")
                if result_cb is not None:
                    result_cb(entry["line"], "УК + АК")
            elif CAT_ADMIN in categories:
                result.admin_only.append(entry["line"])
                log("   Найдено: административная судимость (место отбывания начинается с 'КПЗ') -> 'АК'\n")
                if result_cb is not None:
                    result_cb(entry["line"], "АК")
            elif CAT_CRIMINAL in categories:
                result.criminal_only.append(entry["line"])
                log("   Найдено: уголовная судимость (СИЗО/Федеральная тюрьма) -> 'УК'\n")
                if result_cb is not None:
                    result_cb(entry["line"], "УК")
            else:
                result.skipped += 1
                log("   Совпадений не найдено -> пропущено\n")
    except StopRequested:
        result.stopped_early = True
        log("\nОстановлено пользователем.")

    result.total_time = time.time() - run_start
    if durations:
        result.avg_time = sum(durations) / len(durations)
        result.min_time = min(durations)
        result.max_time = max(durations)
        result.rate_per_min = (len(durations) / result.total_time * 60) if result.total_time > 0 else 0.0
        log(
            "\n--- Статистика времени ---\n"
            f"Затрачено всего: {_format_duration(result.total_time)}\n"
            f"Среднее время на человека: {result.avg_time:.2f} с\n"
            f"Минимальное время: {result.min_time:.2f} с\n"
            f"Максимальное время: {result.max_time:.2f} с\n"
            f"Скорость: {result.rate_per_min:.1f} чел/мин ({result.rate_per_min / 60:.2f} чел/сек)\n"
        )

    return result
