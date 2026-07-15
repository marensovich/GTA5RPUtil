# -*- coding: utf-8 -*-
"""
Настройки автоматизации, вынесенные из констант в отдельный объект,
чтобы их можно было редактировать через GUI (и сохранять/загружать
из файла настроек).
"""

import json
from dataclasses import dataclass, asdict, field

from ocr_setup import resource_path, app_base_dir

BASE_DIR = app_base_dir()

CONFIG_FILE = BASE_DIR / "gui_settings.json"

# Режимы классификации судимостей
MODE_ADMIN = "admin"        # только административные (КПЗ LSPD / КПЗ LSSD)
MODE_CRIMINAL = "criminal"  # только уголовные (СИЗО / федеральная тюрьма)
MODE_BOTH = "both"          # оба вида, раздельно в одном файле

MODE_LABELS = {
    MODE_ADMIN: "Административные (место отбывания начинается с 'КПЗ')",
    MODE_CRIMINAL: "Уголовные (СИЗО / федеральная тюрьма)",
    MODE_BOTH: "Оба вида (раздельно в одном файле)",
}

# Административная судимость определяется по тому, что "место отбывания
# наказания" НАЧИНАЕТСЯ с "КПЗ" (КПЗ LSPD, КПЗ LSSD и любые другие
# варианты после "КПЗ") — поэтому одного общего слова достаточно, не
# нужно перечислять каждый конкретный участок отдельно.
DEFAULT_ADMIN_KEYWORDS = ["кпз"]
DEFAULT_CRIMINAL_KEYWORDS = ["следственный изолятор", "федеральная тюрьма"]

INPUT_FILE = "file"
INPUT_TEXT = "text"


@dataclass
class Settings:
    # Входной файл (или вставленный текст — см. input_source). Выходного
    # файла больше нет — результаты живут только в интерфейсе программы.
    input_file: str = str(BASE_DIR / "input.txt")

    # "file" — читать input_file, "text" — использовать input_text
    # (вставленный прямо в программу список записей)
    input_source: str = INPUT_FILE
    input_text: str = ""

    # Режим классификации
    mode: str = MODE_CRIMINAL

    # Ключевые слова (в нижнем регистре, сравнение по вхождению подстроки)
    admin_keywords: list = field(default_factory=lambda: list(DEFAULT_ADMIN_KEYWORDS))
    criminal_keywords: list = field(default_factory=lambda: list(DEFAULT_CRIMINAL_KEYWORDS))

    # Окно игры
    target_process_name: str = "GTA5.exe"
    reactivate_each_entry: bool = True
    capture_all_monitors: bool = True

    # Полупрозрачное окошко поверх игры с ходом проверки (прогресс, кто
    # проверяется сейчас, статистика времени) — можно выключить, если
    # мешает или перекрывает интерфейс игры.
    show_overlay: bool = True

    # Горячая клавиша аварийной остановки (работает даже когда окно
    # программы не в фокусе — например, когда активна игра)
    stop_hotkey: str = "f3"

    # Поиск элементов на экране. action_delay/activation_delay/scroll_delay —
    # пауза между "прочими" действиями (клик, активация окна, прокрутка).
    # results_load_delay — отдельная пауза именно между нажатием кнопки
    # "Поиск" и началом анализа результатов (там реально нужно подождать
    # загрузку данных, поэтому она больше остальных).
    confidence: float = 0.8
    action_delay: float = 0.1
    clear_field_backspace_count: int = 30
    activation_delay: float = 0.1
    results_load_delay: float = 0.3
    # Пауза между нажатиями клавиш при вводе значений, СОДЕРЖАЩИХ буквы
    # (поиск по имени вида 'Wilson_Aether') — для чисто цифровых номеров
    # паспорта набор всегда мгновенный (interval=0), это не трогает.
    # Подчёркивание вводится через Shift+Minus, и при мгновенном наборе
    # веб-интерфейс игры иногда не успевал обработать нажатие модификатора
    # и обрывал ввод, оставляя в поле только последний символ.
    name_entry_type_interval: float = 0.05

    # Область результатов и OCR
    results_panel_left_offset: int = -870
    results_panel_top_offset: int = 0
    results_panel_width: int = 1375
    results_panel_height: int = 600

    max_scroll_attempts: int = 15
    scroll_amount: int = -400
    scroll_delay: float = 0.1

    # Область текста 'Паспорт #N' на странице результатов — читается только
    # для записей, которые искались по имени (см. is_name_search в
    # parse_entries_from_text), и дописывается в скобках к результату,
    # чтобы было видно, какому именно паспорту соответствует найденное имя.
    # Заданы как смещение от той же найденной шапки таблицы результатов
    # (RESULTS_HEADER_IMAGE), что и results_panel_* выше — текст 'Паспорт'
    # находится ВЫШЕ и ЛЕВЕЕ шапки, поэтому оба смещения отрицательные.
    passport_number_left_offset: int = -667
    passport_number_top_offset: int = -70
    passport_number_width: int = 230
    passport_number_height: int = 40

    # Вкладка "Фракция": область таблицы участников (столбцы "Имя" и
    # "Последний вход"), заданная как смещение от найденной шапки таблицы
    # (FACTION_HEADER_IMAGE) — калибруется под конкретный экран так же, как
    # область результатов проверки судимостей выше.
    # Смещение подобрано так, чтобы НЕ захватывать круглую аватарку и точку
    # "онлайн" слева от имени — если их включить в захват, OCR иногда
    # принимает лицо/цвета аватарки за "буквы" и выдаёт мусорные строки.
    faction_name_col_left_offset: int = 104
    faction_name_col_width: int = 260
    faction_login_col_left_offset: int = 905
    faction_login_col_width: int = 230
    faction_panel_top_offset: int = 0
    faction_panel_height: int = 500

    # ВАЖНО: это ТОЛЬКО страховка от бесконечного цикла, а не расчётное
    # число прокруток списка — реальная остановка происходит по содержимому
    # (см. faction_stop_after_no_new_streak / детект "экран не изменился"),
    # обычно намного раньше этого числа. Стоит по умолчанию с большим
    # запасом, т.к. заранее не известно, сколько реальных пикселей сдвигает
    # список одна прокрутка колёсиком на конкретном экране/в конкретной
    # игре — если это мало, прокруток может понадобиться в разы больше,
    # чем кажется по числу участников и высоте одной "страницы" списка.
    faction_max_scroll_attempts: int = 600
    # ВАЖНО: должно быть ЗАМЕТНО меньше, чем нужно для полной страницы
    # списка (faction_panel_height) — иначе соседние прокрутки почти не
    # перекрываются, и часть строк между ними никогда не попадает ни в
    # один снимок экрана (тихо пропускается, а не дублируется). Признак
    # в логе: "новых участников" почти равно "строк распознано" на КАЖДОЙ
    # попытке — если так, значение здесь слишком большое, уменьшайте.
    #
    # -700 в тесте прокручивало ПОЛНУЮ страницу (~10-11 новых из ~10-11
    # строк — то есть почти нулевой перехлёст, отсюда пропуски). Целевой
    # результат — 6-7 новых на прокрутку (~3-4 строки перехлёста из ~10-11
    # видимых) — линейно от той же точки калибровки даёт ~-440.
    faction_scroll_amount: int = -440
    faction_scroll_delay: float = 0.15
    # Точка, куда программа наводит курсор перед прокруткой колёсиком —
    # по умолчанию центр колонки 'Имя', смещённый на столько пикселей
    # вправо (чтобы не попадать на аватарку/иконки и наводиться туда, где
    # прокрутка списка точно работает).
    faction_scroll_cursor_x_offset: int = 150
    # Сколько прокруток ПОДРЯД не должны приносить ни одного нового
    # участника, прежде чем считать, что список закончился (и остановиться
    # раньше max_scroll_attempts) — надёжнее, чем ждать побитового
    # совпадения скриншота, т.к. OCR-шум иногда чуть меняет картинку даже
    # когда содержимое списка уже не меняется. Стоит с запасом (не 1-2), т.к.
    # при небольшом перехлёсте между прокрутками несколько подряд экранов
    # МОГУТ не принести ничего нового, даже если список ещё не закончился.
    faction_stop_after_no_new_streak: int = 20

    # Область текста "Участников: N" вверху страницы списка — заявленное
    # общее число участников, читается один раз через OCR и используется
    # как ориентир: если после прокрутки вниз до конца собрано МЕНЬШЕ,
    # чем заявлено, список прокручивается обратно наверх и сканируется
    # заново (см. faction_extra_passes), пока не наберётся заявленное
    # число или доп. проход не перестанет находить новых участников.
    # Заданы как смещение от найденной шапки таблицы (top — отрицательный,
    # т.к. текст находится ВЫШЕ шапки колонок).
    faction_total_left_offset: int = 960
    faction_total_top_offset: int = -95
    faction_total_width: int = 310
    faction_total_height: int = 35
    # Сколько раз повторять цикл "наверх и заново сканировать", пока
    # собранное число не достигнет заявленного — страховка от бесконечного
    # цикла на случай, если счётчик 'Участников' неточен или часть записей
    # физически недоступна OCR (например, скрыта/не прогружается).
    faction_extra_passes: int = 3

    # Tesseract (пусто = автоопределение: встроенный в exe, иначе системный)
    tesseract_cmd_override: str = ""

    # Отладка
    debug_save_ocr_images: bool = False

    def to_dict(self):
        return asdict(self)

    @classmethod
    def load(cls) -> "Settings":
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                defaults = asdict(cls())
                defaults.update({k: v for k, v in data.items() if k in defaults})
                return cls(**defaults)
            except Exception:
                pass
        return cls()

    def save(self):
        try:
            CONFIG_FILE.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass


TEMPLATES_DIR = resource_path("templates")
FIELD_IMAGE = TEMPLATES_DIR / "field_template.png"
BUTTON_IMAGE = TEMPLATES_DIR / "button_template.png"
RESULTS_HEADER_IMAGE = TEMPLATES_DIR / "results_header_template.png"
FACTION_HEADER_IMAGE = TEMPLATES_DIR / "faction_header_template.png"

LOGO_IMAGE = resource_path("logo.jpg")
