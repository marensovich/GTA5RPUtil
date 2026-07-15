# -*- coding: utf-8 -*-
"""
GUI (PySide6/Qt, тёмная тема Catppuccin Mocha, боковая навигация, лого
GTA5 RP-сервера).

Плоский минималистичный стиль (без градиентов и теней, моноширинный
шрифт) — оформление сделано по образцу GTA5RPAntiCuff, чтобы у всех
"инструментов для GTA5RP" был единый визуальный язык. Всё оформление
живёт в STYLE_SHEET ниже; отдельного модуля кастомных виджетов нет —
Qt/QSS делает нативно то, что в Tkinter приходилось бы рисовать вручную.

Помимо главного окна здесь же живёт OverlayWindow — маленькое
полупрозрачное окошко без рамки, всегда поверх остальных окон (в т.ч.
игры), которое показывает ход проверки, пока свёрнут/не в фокусе GUI.
"""

import html
import sys
import threading
import traceback
import webbrowser

from PySide6.QtCore import QDate, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import automation
import updater
from ocr_setup import resolve_tesseract_cmd
from settings import (
    INPUT_FILE,
    INPUT_TEXT,
    LOGO_IMAGE,
    MODE_ADMIN,
    MODE_BOTH,
    MODE_CRIMINAL,
    MODE_LABELS,
    Settings,
)

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

APP_NAME = "GTA5RP Util"
APP_VERSION_DISPLAY = f"v.{updater.APP_VERSION}"
APP_TITLE = f"{APP_NAME} {APP_VERSION_DISPLAY}"
DEVELOPER_INFO = f"{APP_VERSION_DISPLAY}  ·  Разработчик: Bushido_Manhattan  ·  Discord: marensov"

# ---------------------------------------------------------------------------
# Палитра — Catppuccin Mocha, как в GTA5RPAntiCuff (плоский минималистичный
# стиль без градиентов/теней, моноширинный шрифт для всего интерфейса —
# единый визуальный язык между "инструментами для GTA5RP").
# ---------------------------------------------------------------------------
BG_DARK = "#1e1e2e"      # base — фон окна
BG_DARKER = "#181825"    # mantle — шапка, подвал, боковая панель
BG_PANEL = "#252535"     # surface — карточки, поля ввода
BG_INPUT = "#252535"
FG_TEXT = "#cdd6f4"
FG_MUTED = "#6c7086"
FG_DIM = "#585b70"
ACCENT = "#cba6f7"       # mauve
ACCENT_TEXT_ON = "#1e1e2e"
BORDER = "#313244"
BORDER_LIGHT = "#45475a"
ERROR_COLOR = "#f38ba8"  # red
SUCCESS_COLOR = "#a6e3a1"  # green
WARNING_COLOR = "#f9e2af"  # yellow
BLUE = "#89b4fa"
PEACH = "#fab387"
FONT_FAMILY = "Consolas, 'Cascadia Code', monospace"

NAV_ITEMS = [
    ("home", "🏠", "Главная"),
    ("check", "🔍", "Проверка судимостей"),
    ("faction", "🏛", "Фракция"),
    ("log", "📜", "Лог"),
    ("settings", "⚙", "Настройки"),
]

# Короткие метки категорий судимостей, показываемые в результатах:
# уголовная — "УК", административная — "АК", обе сразу — "УК + АК".
RESULT_CATEGORY_KEY = {
    "АК": "admin",
    "УК": "criminal",
    "УК + АК": "both",
}
CATEGORY_COLOR = {
    "АК": BLUE,
    "УК": ERROR_COLOR,
    "УК + АК": PEACH,
}

STYLE_SHEET = f"""
QWidget {{
    background-color: {BG_DARK};
    color: {FG_TEXT};
    font-family: {FONT_FAMILY};
    font-size: 10pt;
}}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {FG_MUTED}; font-size: 8.5pt; }}
QLabel#cardTitle {{ color: {ACCENT}; font-weight: bold; font-size: 10.5pt; background: transparent; }}

QFrame#card {{
    background-color: {BG_PANEL};
    border-radius: 8px;
    border: 1px solid {BORDER};
}}

QFrame#header {{
    background-color: {BG_DARKER};
    border-bottom: 1px solid {BORDER};
}}
QFrame#footer {{
    background-color: {BG_DARKER};
    border-top: 1px solid {BORDER};
}}
QFrame#updateBanner {{ background-color: {ACCENT}; }}
QLabel#headerTitle {{ font-size: 15pt; font-weight: bold; color: {ACCENT}; background: transparent; }}
QLabel#headerSubtitle {{ color: {FG_MUTED}; font-size: 9pt; background: transparent; }}
QLabel#statusDot {{ font-size: 13pt; background: transparent; }}
QLabel#statusText {{ color: {FG_MUTED}; font-size: 9pt; background: transparent; }}
QLabel#footerLink {{ color: {ACCENT}; font-size: 8.5pt; text-decoration: underline; background: transparent; }}

QFrame#sidebar {{ background-color: {BG_DARKER}; border-right: 1px solid {BORDER}; }}
QPushButton#navItem {{
    background: transparent;
    text-align: left;
    padding: 12px 14px;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    color: {FG_MUTED};
    font-size: 9.5pt;
}}
QPushButton#navItem:hover {{ background-color: {BG_PANEL}; }}
QPushButton#navItem:checked {{
    background-color: {BG_PANEL};
    color: {ACCENT};
    border-left: 3px solid {ACCENT};
    font-weight: bold;
}}

QPushButton {{
    background-color: {BG_PANEL};
    color: {FG_TEXT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover {{ background-color: {BORDER_LIGHT}; }}
QPushButton:pressed {{ background-color: {BORDER}; }}
QPushButton:disabled {{ background-color: {BG_DARKER}; color: {FG_DIM}; border: 1px solid {BORDER}; }}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    border: none;
    color: {ACCENT_TEXT_ON};
    font-weight: bold;
}}
QPushButton#primaryButton:hover {{ background-color: #d8bdf9; }}
QPushButton#primaryButton:pressed {{ background-color: #b48eea; }}
QPushButton#primaryButton:disabled {{ background-color: {BORDER_LIGHT}; color: {FG_DIM}; }}

QPushButton#dangerButton {{
    background-color: {ERROR_COLOR};
    border: none;
    color: {ACCENT_TEXT_ON};
    font-weight: bold;
}}
QPushButton#dangerButton:hover {{ background-color: #f5a3bb; }}
QPushButton#dangerButton:pressed {{ background-color: #d97992; }}
QPushButton#dangerButton:disabled {{ background-color: {BORDER_LIGHT}; color: {FG_DIM}; }}

QPushButton#linkButton {{
    background: transparent;
    border: none;
    color: {ACCENT};
    text-decoration: underline;
    padding: 0;
}}
QPushButton#linkButton:hover {{ color: #d8bdf9; }}

QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT_ON};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled {{ background-color: {BG_DARKER}; color: {FG_DIM}; }}

QComboBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
}}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    color: {FG_TEXT};
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT_ON};
    border: 1px solid {BORDER};
    outline: none;
}}

QSpinBox, QDoubleSpinBox, QDateEdit {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 6px;
}}
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{ border: 1px solid {ACCENT}; }}
QDateEdit QAbstractItemView {{
    background-color: {BG_PANEL};
    color: {FG_TEXT};
    selection-background-color: {ACCENT};
    selection-color: {ACCENT_TEXT_ON};
    border: 1px solid {BORDER};
    outline: none;
}}

QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator {{ border-radius: 4px; border: 1px solid {BORDER_LIGHT}; background: {BG_PANEL}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QRadioButton::indicator {{ border-radius: 8px; border: 1px solid {BORDER_LIGHT}; background: {BG_PANEL}; }}
QRadioButton::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}

QSlider::groove:horizontal {{
    height: 6px;
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {FG_TEXT};
    border: 2px solid {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}

QProgressBar {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    min-height: 14px;
    max-height: 14px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 5px; }}

QScrollBar:vertical {{ background: {BG_DARK}; width: 12px; border-radius: 6px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_LIGHT}; border-radius: 6px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {FG_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}

QWidget#overlayRoot {{ background: transparent; }}
QFrame#overlayCard {{
    background: rgba(24, 24, 37, 235);
    border: 1px solid {ACCENT};
    border-radius: 10px;
}}
QLabel#overlayTitle {{ color: {ACCENT}; font-weight: bold; font-size: 10pt; background: transparent; }}
QLabel#overlayProgress {{ color: {FG_TEXT}; font-weight: bold; font-size: 10pt; background: transparent; }}
QLabel#overlayLine {{ color: {FG_TEXT}; font-size: 9pt; background: transparent; }}
QLabel#overlayMuted {{ color: {FG_MUTED}; font-size: 8pt; background: transparent; }}
"""


def make_card(title=None):
    """Плоская карточка (без теней/градиентов — тот же минималистичный
    стиль, что и в GTA5RPAntiCuff) с вертикальным layout'ом внутри
    (card, layout — добавляйте виджеты в layout)."""
    card = QFrame()
    card.setObjectName("card")

    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(8)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("cardTitle")
        layout.addWidget(lbl)
    return card, layout


def labeled_row(label_text, widget, label_width=280, hint=None):
    """Строка 'подпись + виджет', опционально с приглушённой пояснительной
    строкой снизу (комментарий к настройке — что это и когда менять)."""
    wrap = QWidget()
    wrap.setStyleSheet("background: transparent;")
    outer = QVBoxLayout(wrap)
    outer.setContentsMargins(0, 2, 0, 10 if hint else 4)
    outer.setSpacing(3)

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(label_width)
    row.addWidget(lbl)
    row.addWidget(widget)
    row.addStretch()
    outer.addLayout(row)

    if hint:
        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("muted")
        hint_lbl.setWordWrap(True)
        outer.addWidget(hint_lbl)
    return wrap


def make_slider(minv, maxv, value, decimals=2, step=None):
    """QSlider работает только с int, поэтому реальные float-значения
    (0.0-1.0 для confidence, секунды для пауз) масштабируются на
    10**decimals и хранятся в свойствах виджета — slider_value() читает
    обратно."""
    scale = 10 ** decimals
    slider = QSlider(Qt.Horizontal)
    slider.setMinimum(round(minv * scale))
    slider.setMaximum(round(maxv * scale))
    step_scaled = round((step if step else (maxv - minv) / 20 or 1) * scale) or 1
    slider.setSingleStep(step_scaled)
    slider.setPageStep(step_scaled)
    slider.setValue(round(value * scale))
    slider.setProperty("_scale", scale)
    slider.setProperty("_decimals", decimals)
    slider.setFixedWidth(260)
    return slider


def slider_value(slider) -> float:
    scale = slider.property("_scale") or 1
    return slider.value() / scale


def slider_field(title, slider, hint=None, suffix=""):
    """Строка настройки-ползунка: подпись + текущее значение справа,
    сам слайдер, и пояснение снизу (что регулирует и когда трогать)."""
    wrap = QWidget()
    wrap.setStyleSheet("background: transparent;")
    v = QVBoxLayout(wrap)
    v.setContentsMargins(0, 2, 0, 12)
    v.setSpacing(3)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(title)
    top.addWidget(lbl)
    top.addStretch()
    value_lbl = QLabel("")
    value_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold;")
    top.addWidget(value_lbl)
    v.addLayout(top)
    v.addWidget(slider)

    if hint:
        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("muted")
        hint_lbl.setWordWrap(True)
        v.addWidget(hint_lbl)

    decimals = slider.property("_decimals") or 0

    def update_label(_=None):
        value_lbl.setText(f"{slider_value(slider):.{decimals}f}{suffix}")

    slider.valueChanged.connect(update_label)
    update_label()
    return wrap


def format_seconds(seconds: float) -> str:
    seconds = max(0.0, seconds or 0.0)
    minutes, secs = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}ч {minutes:02d}м {secs:02d}с"
    if minutes:
        return f"{minutes}м {secs:02d}с"
    return f"{secs}с"


class PlainTextEdit(QTextEdit):
    """QTextEdit, который принудительно вставляет вставленный текст без
    форматирования (никаких унаследованных цветов/шрифтов из буфера
    обмена — например, если скопировать список персонажей из Discord
    или таблицы, где текст цветной) — весь текст остаётся обычным белым,
    как задаёт стиль виджета."""

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)


# ---------------------------------------------------------------------------
# Оверлей поверх игры: прогресс, кто проверяется сейчас, статистика времени
# ---------------------------------------------------------------------------
class OverlayWindow(QWidget):
    # Ширина окна фиксирована; строки с переменным текстом (текущая
    # запись, статистика) держим на ЗАРАНЕЕ известной высоте (одна и две
    # строки соответственно, с обрезкой по многоточию) — иначе при смене
    # текста layout пересчитывает sizeHint() и Qt пытается изменить уже
    # показанное окно с фиксированной шириной, из-за чего Windows иногда
    # не может применить геометрию с первой попытки (безобидный, но
    # шумный warning "QWindowsWindow::setGeometry: Unable to set...").
    WIDTH = 300
    _TEXT_WIDTH = WIDTH - 28 - 12  # минус отступы карточки и небольшой запас

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setObjectName("overlayRoot")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._drag_pos = None
        self.setFixedWidth(self.WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame(self)
        card.setObjectName("overlayCard")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        self.title_lbl = QLabel("🔍 Проверка судимостей")
        self.title_lbl.setObjectName("overlayTitle")
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        self.progress_lbl = QLabel("0 / 0")
        self.progress_lbl.setObjectName("overlayProgress")
        title_row.addWidget(self.progress_lbl)
        layout.addLayout(title_row)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.bar)

        self.current_lbl = QLabel("Ожидание запуска…")
        self.current_lbl.setObjectName("overlayLine")
        self.current_lbl.setWordWrap(False)
        self.current_lbl.setFixedHeight(self.current_lbl.fontMetrics().height() + 2)
        layout.addWidget(self.current_lbl)

        self.stats_lbl = QLabel("")
        self.stats_lbl.setObjectName("overlayMuted")
        self.stats_lbl.setWordWrap(False)
        self.stats_lbl.setFixedHeight(2 * self.stats_lbl.fontMetrics().height() + 4)
        layout.addWidget(self.stats_lbl)

        hint = QLabel("Перетащите за окно, чтобы передвинуть")
        hint.setObjectName("overlayMuted")
        layout.addWidget(hint)

        # Высота теперь не меняется от смены текста — фиксируем размер
        # окна один раз здесь же, чтобы Windows сразу знал финальную
        # геометрию (никаких последующих попыток resize после show()).
        self.adjustSize()
        self.setFixedHeight(self.height())

    def _elide(self, label: QLabel, text: str, max_lines: int = 1):
        """Обрезает текст многоточием по ширине окна вместо переноса
        строк — иначе высота строки менялась бы вместе с длиной текста
        (имя персонажа, число записей)."""
        metrics = label.fontMetrics()
        if max_lines <= 1:
            label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, self._TEXT_WIDTH))
            return
        lines = text.split("\n")
        elided = [metrics.elidedText(line, Qt.TextElideMode.ElideRight, self._TEXT_WIDTH) for line in lines[:max_lines]]
        label.setText("\n".join(elided))

    def set_title(self, text: str):
        self.title_lbl.setText(text)

    def reset(self, total: int):
        self.bar.setVisible(True)
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(0)
        self.progress_lbl.setText(f"0 / {total}")
        self._elide(self.current_lbl, "Инициализация…")
        self.stats_lbl.setText("")

    def reset_faction(self):
        # У парсинга фракции нет заранее известного "итога" (сколько всего
        # прокруток реально понадобится) — прогресс-бар с произвольным
        # верхним пределом (макс. попыток) только вводит в заблуждение,
        # выглядя как "осталось ещё много", даже если сканирование вот-вот
        # само остановится, обнаружив конец списка. Поэтому для фракции
        # бар скрыт — важно только число уже найденных участников.
        self.bar.setVisible(False)
        self.progress_lbl.setText("0")
        self._elide(self.current_lbl, "Инициализация…")
        self.stats_lbl.setText("")

    def set_faction_progress(self, collected: int):
        self.progress_lbl.setText(str(collected))
        self._elide(self.current_lbl, f"Собрано: {collected}")

    def set_current(self, idx: int, total: int, label: str):
        if self.bar.maximum() != max(total, 1):
            self.bar.setRange(0, max(total, 1))
        self.progress_lbl.setText(f"{idx}/{total}")
        self._elide(self.current_lbl, f"Сейчас: {label}")

    def set_stats(self, data: dict):
        self.bar.setValue(data["idx"])
        self._elide(
            self.stats_lbl,
            f"Прошло: {format_seconds(data['elapsed'])}  ·  Осталось: ~{format_seconds(data.get('eta_seconds', 0))}\n"
            f"На чел.: сред. {data['avg']:.1f}с, мин {data['min']:.1f}с, макс {data['max']:.1f}с  ·  "
            f"{data['rate_per_min']:.1f} чел/мин",
            max_lines=2,
        )

    def set_finished(self, text: str):
        self._elide(self.current_lbl, text)

    def position_near(self, rect):
        """rect — (left, top, right, bottom) окна игры в экранных
        координатах, либо None (тогда — правый верхний угол основного
        монитора)."""
        margin = 24
        if rect is not None:
            left, top, right, bottom = rect
            x, y = right - self.width() - margin, top + margin
        else:
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
            if geo is not None:
                x, y = geo.right() - self.width() - margin, geo.top() + margin
            else:
                x, y = 100, 100
        self.move(int(x), int(y))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Фоновый поток автоматизации (QThread + сигналы — потокобезопасно "из
# коробки", в отличие от ручного queue+after() в Tkinter-версии)
# ---------------------------------------------------------------------------
class AutomationWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    result = Signal(str, str)
    current = Signal(int, int, str)
    stats = Signal(dict)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: Settings, stop_event: threading.Event):
        super().__init__()
        self.settings = settings
        self.stop_event = stop_event

    def run(self):
        try:
            result = automation.run(
                self.settings,
                log=self.log.emit,
                stop_event=self.stop_event,
                progress_cb=self.progress.emit,
                result_cb=self.result.emit,
                current_cb=self.current.emit,
                stats_cb=self.stats.emit,
            )
            self.finished.emit(result)
        except automation.AutomationError as e:
            self.failed.emit(str(e))
        except Exception:
            self.failed.emit(traceback.format_exc())


class FactionWorker(QObject):
    log = Signal(str)
    count = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: Settings, stop_event: threading.Event):
        super().__init__()
        self.settings = settings
        self.stop_event = stop_event

    def run(self):
        try:
            result = automation.collect_faction_members(
                self.settings,
                log=self.log.emit,
                stop_event=self.stop_event,
                count_cb=self.count.emit,
            )
            self.finished.emit(result)
        except automation.AutomationError as e:
            self.failed.emit(str(e))
        except Exception:
            self.failed.emit(traceback.format_exc())


class HotkeyBridge(QObject):
    """keyboard.add_hotkey зовёт колбэк из своего собственного потока —
    Signal.emit() потокобезопасен и сам домаршалит вызов в Qt-поток GUI."""
    triggered = Signal()


class UpdateBridge(QObject):
    found = Signal(str, str)


# ---------------------------------------------------------------------------
# Главное окно
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 800)
        self.setMinimumSize(960, 680)

        self.settings = Settings.load()
        self.stop_event = threading.Event()
        self.thread = None
        self.worker = None
        self.running = False
        self._active_stop_button = None
        self._faction_mode = None
        self._hotkey_registered = None
        self._counts = {"admin": 0, "criminal": 0, "both": 0}
        self._pulse_state = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)

        self.hotkey_bridge = HotkeyBridge()
        self.hotkey_bridge.triggered.connect(self._on_hotkey_stop)
        self.update_bridge = UpdateBridge()
        self.update_bridge.found.connect(self._show_update_banner)

        self.overlay = OverlayWindow()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            try:
                self.tray = QSystemTrayIcon(QIcon(str(LOGO_IMAGE)), self)
                self.tray.setToolTip(APP_NAME)
            except Exception:
                self.tray = None

        self._build_ui()
        self._log_tesseract_status()
        self._refresh_processes(quiet=True)
        self._start_update_check()

    # ------------------------------------------------------------------
    # Каркас окна
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())
        self.update_banner = self._build_update_banner()
        root_layout.addWidget(self.update_banner)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_sidebar())

        content_wrap = QWidget()
        content_wrap_layout = QVBoxLayout(content_wrap)
        content_wrap_layout.setContentsMargins(16, 12, 16, 12)
        self.stack = QStackedWidget()
        content_wrap_layout.addWidget(self.stack)
        body_layout.addWidget(content_wrap, 1)

        root_layout.addWidget(body, 1)
        root_layout.addWidget(self._build_footer())

        self.pages = {}
        for key, _icon, _label in NAV_ITEMS:
            page = QWidget()
            self.pages[key] = page
            self.stack.addWidget(page)

        self._build_home_page(self.pages["home"])
        self._build_check_page(self.pages["check"])
        self._build_faction_page(self.pages["faction"])
        self._build_log_page(self.pages["log"])
        self._build_settings_page(self.pages["settings"])

        self._show_page("home")

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(78)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 10, 20, 10)

        try:
            icon_pix = QPixmap(str(LOGO_IMAGE)).scaled(
                40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon_pix)
            layout.addWidget(icon_lbl)
            self.setWindowIcon(QIcon(str(LOGO_IMAGE)))
        except Exception:
            pass

        layout.addSpacing(16)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        t = QLabel(f"{APP_NAME} {APP_VERSION_DISPLAY}")
        t.setObjectName("headerTitle")
        st = QLabel("Проверка судимостей — автоматизация поиска и OCR-проверки")
        st.setObjectName("headerSubtitle")
        title_box.addWidget(t)
        title_box.addWidget(st)
        title_wrap = QWidget()
        title_wrap.setStyleSheet("background: transparent;")
        title_wrap.setLayout(title_box)
        layout.addWidget(title_wrap)
        layout.addStretch()

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setStyleSheet(f"color: {FG_MUTED};")
        self.status_text = QLabel("Готово")
        self.status_text.setObjectName("statusText")
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_text)

        return header

    def _build_update_banner(self):
        banner = QFrame()
        banner.setObjectName("updateBanner")
        banner.setVisible(False)
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(14, 6, 14, 6)
        self._update_label = QLabel("")
        self._update_label.setStyleSheet(f"color: {ACCENT_TEXT_ON}; font-weight: bold; background: transparent;")
        layout.addWidget(self._update_label)

        self._update_link_btn = QPushButton("Скачать →")
        self._update_link_btn.setStyleSheet(
            f"background: transparent; color: {ACCENT_TEXT_ON}; font-weight: bold; "
            "text-decoration: underline; padding: 0;"
        )
        self._update_link_btn.setCursor(Qt.PointingHandCursor)
        layout.addSpacing(14)
        layout.addWidget(self._update_link_btn)
        layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setStyleSheet(
            f"background: transparent; color: {ACCENT_TEXT_ON}; font-weight: bold; padding: 0 4px;"
        )
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(lambda: banner.setVisible(False))
        layout.addWidget(close_btn)

        return banner

    def _build_footer(self):
        footer = QFrame()
        footer.setObjectName("footer")
        footer.setFixedHeight(48)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addStretch()

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        dev_lbl = QLabel(DEVELOPER_INFO)
        dev_lbl.setObjectName("muted")
        dev_lbl.setAlignment(Qt.AlignCenter)
        text_box.addWidget(dev_lbl)

        link = QPushButton("исходный код")
        link.setObjectName("footerLink")
        link.setFlat(True)
        link.setCursor(Qt.PointingHandCursor)
        link.setStyleSheet(
            f"background: transparent; border: none; color: {ACCENT}; "
            "text-decoration: underline; padding: 0; font-size: 8.5pt;"
        )
        link.clicked.connect(lambda: webbrowser.open(f"https://github.com/{updater.GITHUB_REPO}"))
        text_box.addWidget(link, alignment=Qt.AlignCenter)

        text_wrap = QWidget()
        text_wrap.setStyleSheet("background: transparent;")
        text_wrap.setLayout(text_box)
        layout.addWidget(text_wrap)
        layout.addStretch()
        return footer

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(2)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        for key, icon, label in NAV_ITEMS:
            btn = QPushButton(f"  {icon}   {label}")
            btn.setObjectName("navItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _checked, k=key: self._show_page(k))
            layout.addWidget(btn)
            self.nav_group.addButton(btn)
            self.nav_buttons[key] = btn

        layout.addStretch()
        return sidebar

    def _show_page(self, key):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)

    # ------------------------------------------------------------------
    # Страница "Проверка судимостей" (режим + игра + ввод + результаты)
    # ------------------------------------------------------------------
    def _build_home_page(self, page):
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        outer.addLayout(layout)

        intro = QLabel(
            "Общие настройки игры — применяются ко всем разделам программы "
            "('Проверка судимостей' и 'Фракция')."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        game_card, game_layout = make_card("Игра")
        proc_row = QWidget()
        proc_row.setStyleSheet("background: transparent;")
        proc_row_layout = QHBoxLayout(proc_row)
        proc_row_layout.setContentsMargins(0, 0, 0, 0)
        proc_row_layout.addWidget(QLabel("Процесс окна:"))
        self.process_combo = QComboBox()
        self.process_combo.setEditable(True)
        self.process_combo.setCurrentText(self.settings.target_process_name)
        self.process_combo.setFixedWidth(220)
        proc_row_layout.addWidget(self.process_combo)
        refresh_btn = QPushButton("⟳ Обновить")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_processes)
        proc_row_layout.addWidget(refresh_btn)
        proc_row_layout.addStretch()
        game_layout.addWidget(proc_row)

        self.chk_reactivate = QCheckBox("Активировать окно перед каждой записью")
        self.chk_reactivate.setChecked(self.settings.reactivate_each_entry)
        game_layout.addWidget(self.chk_reactivate)
        self.chk_multi_monitor = QCheckBox("Захват всех мониторов")
        self.chk_multi_monitor.setChecked(self.settings.capture_all_monitors)
        game_layout.addWidget(self.chk_multi_monitor)
        self.chk_overlay = QCheckBox("Показывать оверлей с прогрессом поверх игры")
        self.chk_overlay.setChecked(self.settings.show_overlay)
        game_layout.addWidget(self.chk_overlay)

        hotkey_row = QWidget()
        hotkey_row.setStyleSheet("background: transparent;")
        hotkey_row_layout = QHBoxLayout(hotkey_row)
        hotkey_row_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_row_layout.addWidget(QLabel("Горячая клавиша аварийной остановки:"))
        self.hotkey_edit = QLineEdit(self.settings.stop_hotkey)
        self.hotkey_edit.setFixedWidth(80)
        hotkey_row_layout.addWidget(self.hotkey_edit)
        if not KEYBOARD_AVAILABLE:
            warn = QLabel("(модуль 'keyboard' не установлен)")
            warn.setObjectName("muted")
            hotkey_row_layout.addWidget(warn)
        hotkey_row_layout.addStretch()
        game_layout.addWidget(hotkey_row)
        layout.addWidget(game_card)
        layout.addStretch()

    def _build_check_page(self, page):
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        mode_card, mode_layout = make_card("Что сортировать")
        self.mode_group = QButtonGroup(self)
        self.mode_radios = {}
        for mode in (MODE_ADMIN, MODE_CRIMINAL, MODE_BOTH):
            rb = QRadioButton(MODE_LABELS[mode])
            mode_layout.addWidget(rb)
            self.mode_group.addButton(rb)
            self.mode_radios[mode] = rb
        self.mode_radios[self.settings.mode].setChecked(True)
        layout.addWidget(mode_card)

        src_card, src_layout = make_card("Источник входных данных")
        src_row = QHBoxLayout()
        self.input_source_group = QButtonGroup(self)
        self.rb_input_file = QRadioButton("Из файла")
        self.rb_input_text = QRadioButton("Вставленный текст")
        self.input_source_group.addButton(self.rb_input_file)
        self.input_source_group.addButton(self.rb_input_text)
        src_row.addWidget(self.rb_input_file)
        src_row.addWidget(self.rb_input_text)
        src_row.addStretch()
        src_layout.addLayout(src_row)
        layout.addWidget(src_card)

        self.input_file_card, file_layout = make_card()
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Входной файл:"))
        self.input_file_edit = QLineEdit(self.settings.input_file)
        file_row.addWidget(self.input_file_edit, 1)
        browse_btn = QPushButton("Обзор…")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_input)
        file_row.addWidget(browse_btn)
        file_layout.addLayout(file_row)
        layout.addWidget(self.input_file_card)

        self.input_text_card, text_layout = make_card(
            "Список записей (по одной на строку) — 'Имя (номер) N' (N — ранг, опционально) "
            "ИЛИ просто 'Имя Фамилия' (поиск по имени вместо номера паспорта)"
        )
        self.input_text_edit = PlainTextEdit()
        self.input_text_edit.setPlainText(self.settings.input_text)
        self.input_text_edit.setFixedHeight(140)
        self.input_text_edit.setStyleSheet(
            f"color: #ffffff; background-color: {BG_INPUT}; border: 1px solid {BORDER}; "
            "border-radius: 8px; padding: 6px;"
        )
        text_layout.addWidget(self.input_text_edit)
        layout.addWidget(self.input_text_card)

        if self.settings.input_source == INPUT_TEXT:
            self.rb_input_text.setChecked(True)
        else:
            self.rb_input_file.setChecked(True)
        self.rb_input_file.toggled.connect(self._update_input_source_view)
        self._update_input_source_view()

        controls = QHBoxLayout()
        self.btn_start = QPushButton("▶  Старт")
        self.btn_start.setObjectName("primaryButton")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setFixedSize(150, 42)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop = QPushButton("■  Стоп")
        self.btn_stop.setObjectName("dangerButton")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setFixedSize(130, 42)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        controls.addWidget(self.btn_start)
        controls.addSpacing(10)
        controls.addWidget(self.btn_stop)
        controls.addStretch()
        layout.addLayout(controls)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress_label = QLabel("Готово к запуску")
        self.progress_label.setObjectName("muted")
        self.progress_label.setFixedWidth(90)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_label)
        layout.addLayout(progress_row)

        self.check_detail_label = QLabel("")
        self.check_detail_label.setObjectName("muted")
        layout.addWidget(self.check_detail_label)

        self.note_label = QLabel("")
        self.note_label.setObjectName("muted")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        result_card, result_layout = make_card("Результаты (обновляются по ходу выполнения)")
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(160)
        result_layout.addWidget(self.output_text)
        layout.addWidget(result_card, 1)

    def _update_input_source_view(self):
        is_text = self.rb_input_text.isChecked()
        self.input_text_card.setVisible(is_text)
        self.input_file_card.setVisible(not is_text)

    def _build_faction_page(self, page):
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        intro = QLabel(
            "Откройте список участников фракции в игре (должны быть видны колонки 'Имя' и "
            "'Последний вход'), затем запустите нужную операцию ниже."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        collect_card, collect_layout = make_card("Список участников")
        collect_row = QHBoxLayout()
        self.btn_faction_collect = QPushButton("▶  Собрать список")
        self.btn_faction_collect.setObjectName("primaryButton")
        self.btn_faction_collect.setCursor(Qt.PointingHandCursor)
        self.btn_faction_collect.clicked.connect(self._on_faction_collect_start)
        collect_row.addWidget(self.btn_faction_collect)
        collect_row.addStretch()
        collect_layout.addLayout(collect_row)

        self.faction_members_label = QLabel("Ещё не запускалось.")
        self.faction_members_label.setObjectName("muted")
        collect_layout.addWidget(self.faction_members_label)

        self.faction_members_text = QTextEdit()
        self.faction_members_text.setReadOnly(True)
        self.faction_members_text.setMinimumHeight(160)
        collect_layout.addWidget(self.faction_members_text)
        layout.addWidget(collect_card)

        inactive_card, inactive_layout = make_card("Очистка от неактива")
        inactive_hint = QLabel(
            "Программа только СОБИРАЕТ список кандидатов на исключение — сама никого не исключает. "
            "Решение и клик по кнопке исключения (🚫) в игре остаются за вами."
        )
        inactive_hint.setObjectName("muted")
        inactive_hint.setWordWrap(True)
        inactive_layout.addWidget(inactive_hint)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Считать неактивными тех, кто не заходил с:"))
        self.faction_cutoff_date = QDateEdit()
        self.faction_cutoff_date.setCalendarPopup(True)
        self.faction_cutoff_date.setDisplayFormat("dd.MM.yyyy")
        self.faction_cutoff_date.setDate(QDate.currentDate().addDays(-30))
        date_row.addWidget(self.faction_cutoff_date)
        date_row.addStretch()
        inactive_layout.addLayout(date_row)

        inactive_row = QHBoxLayout()
        self.btn_faction_inactive = QPushButton("▶  Найти неактивных")
        self.btn_faction_inactive.setObjectName("primaryButton")
        self.btn_faction_inactive.setCursor(Qt.PointingHandCursor)
        self.btn_faction_inactive.clicked.connect(self._on_faction_inactive_start)
        inactive_row.addWidget(self.btn_faction_inactive)
        inactive_row.addStretch()
        inactive_layout.addLayout(inactive_row)

        self.faction_inactive_label = QLabel("Ещё не запускалось.")
        self.faction_inactive_label.setObjectName("muted")
        inactive_layout.addWidget(self.faction_inactive_label)

        self.faction_inactive_text = QTextEdit()
        self.faction_inactive_text.setReadOnly(True)
        self.faction_inactive_text.setMinimumHeight(160)
        inactive_layout.addWidget(self.faction_inactive_text)
        layout.addWidget(inactive_card, 1)

        status_row = QHBoxLayout()
        self.btn_faction_stop = QPushButton("■  Стоп")
        self.btn_faction_stop.setObjectName("dangerButton")
        self.btn_faction_stop.setCursor(Qt.PointingHandCursor)
        self.btn_faction_stop.setEnabled(False)
        self.btn_faction_stop.clicked.connect(self._on_stop)
        status_row.addWidget(self.btn_faction_stop)
        self.faction_progress_label = QLabel("")
        self.faction_progress_label.setObjectName("muted")
        status_row.addWidget(self.faction_progress_label)
        status_row.addStretch()
        layout.addLayout(status_row)

    def _build_log_page(self, page):
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFontFamily("Consolas")
        layout.addWidget(self.log_text, 1)
        clear_btn = QPushButton("Очистить лог")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(lambda: self.log_text.clear())
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(clear_btn)
        layout.addLayout(row)

    # ------------------------------------------------------------------
    # Страница "Настройки"
    # ------------------------------------------------------------------
    def _build_settings_page(self, page):
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(12)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        s = self.settings

        kw_card, kw_layout = make_card("Ключевые слова (через запятую, регистр не важен)")
        self.admin_kw_edit = QLineEdit(", ".join(s.admin_keywords))
        self.criminal_kw_edit = QLineEdit(", ".join(s.criminal_keywords))
        self.admin_kw_edit.setCursorPosition(0)
        self.criminal_kw_edit.setCursorPosition(0)
        kw_layout.addWidget(labeled_row(
            "Административные (АК):", self.admin_kw_edit,
            hint="Слово(-а), по которым узнаётся административная судимость — ищется как подстрока "
                 "в колонке 'Место отбывания наказания' (по умолчанию 'кпз' находит и 'КПЗ LSPD', и 'КПЗ LSSD').",
        ))
        kw_layout.addWidget(labeled_row(
            "Уголовные (УК):", self.criminal_kw_edit,
            hint="Слово(-а) для уголовной судимости. Меняйте, только если в игре изменилось написание "
                 "('следственный изолятор' / 'федеральная тюрьма' по умолчанию).",
        ))
        layout.addWidget(kw_card)

        recog_card, recog_layout = make_card("Точность и паузы")
        self.confidence_slider = make_slider(0.3, 1.0, s.confidence, decimals=2, step=0.01)
        recog_layout.addWidget(slider_field(
            "Точность распознавания элементов", self.confidence_slider,
            hint="Насколько картинка на экране должна совпасть с эталоном (поле, кнопка, шапка таблицы). "
                 "Выше — надёжнее, но чаще 'не найдено'; ниже — находит охотнее, но рискует промахнуться "
                 "мимо нужного места. Если элементы стабильно не находятся — сдвиньте влево.",
        ))
        self.action_delay_slider = make_slider(0.0, 2.0, s.action_delay, decimals=2, step=0.05)
        recog_layout.addWidget(slider_field(
            "Пауза между действиями", self.action_delay_slider, suffix=" с",
            hint="Задержка между обычными действиями — клик, ввод текста, активация окна. "
                 "Увеличьте, если игра/система не успевает реагировать так же быстро, как программа кликает.",
        ))
        self.activation_delay_slider = make_slider(0.0, 2.0, s.activation_delay, decimals=2, step=0.05)
        recog_layout.addWidget(slider_field(
            "Пауза после активации окна", self.activation_delay_slider, suffix=" с",
            hint="Сколько ждать после переключения фокуса на игру, прежде чем начинать кликать. "
                 "Увеличьте, если окно игры разворачивается/прорисовывается не мгновенно.",
        ))
        self.results_load_delay_slider = make_slider(0.0, 5.0, s.results_load_delay, decimals=2, step=0.1)
        recog_layout.addWidget(slider_field(
            "Пауза загрузки результатов", self.results_load_delay_slider, suffix=" с",
            hint="Между нажатием кнопки 'Поиск' и началом чтения таблицы — здесь реально нужно "
                 "дождаться загрузки данных с сервера, поэтому обычно эта пауза больше остальных.",
        ))
        self.backspace_spin = QSpinBox()
        self.backspace_spin.setRange(0, 200)
        self.backspace_spin.setValue(s.clear_field_backspace_count)
        recog_layout.addWidget(labeled_row(
            "Backspace при очистке поля, раз:", self.backspace_spin,
            hint="Подстраховка на случай, если Ctrl+A не сработал для очистки поля ввода номера паспорта.",
        ))
        self.name_type_interval_slider = make_slider(0.0, 0.3, s.name_entry_type_interval, decimals=2, step=0.01)
        recog_layout.addWidget(slider_field(
            "Пауза между буквами при поиске по имени", self.name_type_interval_slider, suffix=" с",
            hint="Только для записей вида 'Wilson Aether' (номера паспорта всегда вводятся мгновенно). "
                 "Подчёркивание в 'Wilson_Aether' вводится через Shift, и при вводе без пауз "
                 "веб-интерфейс игры иногда не успевает обработать нажатие модификатора и обрывает "
                 "ввод, оставляя в поле только последний символ. Если поле по-прежнему заполняется "
                 "не полностью — увеличьте паузу.",
        ))
        layout.addWidget(recog_card)

        panel_card, panel_layout = make_card("Область таблицы результатов (калибровка под ваш экран)")
        self.panel_left_spin = self._make_int_spin(s.results_panel_left_offset, -5000, 5000)
        self.panel_top_spin = self._make_int_spin(s.results_panel_top_offset, -5000, 5000)
        self.panel_width_spin = self._make_int_spin(s.results_panel_width, 0, 5000)
        self.panel_height_spin = self._make_int_spin(s.results_panel_height, 0, 5000)
        panel_layout.addWidget(labeled_row(
            "Смещение слева от шапки:", self.panel_left_spin,
            hint="В пикселях, от найденной шапки колонки 'Место отбывания наказания' до левого края области чтения.",
        ))
        panel_layout.addWidget(labeled_row(
            "Смещение сверху от шапки:", self.panel_top_spin,
            hint="В пикселях, от шапки до верхнего края области чтения.",
        ))
        panel_layout.addWidget(labeled_row(
            "Ширина области:", self.panel_width_spin,
            hint="Ширина захватываемой области результатов в пикселях.",
        ))
        panel_layout.addWidget(labeled_row(
            "Высота области:", self.panel_height_spin,
            hint="Высота захватываемой области результатов в пикселях. Если OCR не видит нужный текст — "
                 "включите отладочные скриншоты ниже и сверьте, попадает ли текст в рамку.",
        ))
        layout.addWidget(panel_card)

        passport_card, passport_layout = make_card(
            "Область номера паспорта (для записей, найденных по имени)"
        )
        passport_hint = QLabel(
            "Когда запись искалась по имени (например, 'Wilson Aether'), программа дописывает к "
            "результату номер паспорта, прочитанный из текста 'Паспорт #N' над таблицей результатов — "
            "заданного смещением от той же шапки, что и область таблицы результатов выше."
        )
        passport_hint.setObjectName("muted")
        passport_hint.setWordWrap(True)
        passport_layout.addWidget(passport_hint)
        self.passport_left_spin = self._make_int_spin(s.passport_number_left_offset, -5000, 5000)
        self.passport_top_spin = self._make_int_spin(s.passport_number_top_offset, -5000, 5000)
        self.passport_width_spin = self._make_int_spin(s.passport_number_width, 0, 2000)
        self.passport_height_spin = self._make_int_spin(s.passport_number_height, 0, 500)
        passport_layout.addWidget(labeled_row(
            "Смещение слева от шапки:", self.passport_left_spin,
            hint="В пикселях, от шапки таблицы результатов до левого края текста 'Паспорт #N' — "
                 "обычно ОТРИЦАТЕЛЬНОЕ число, т.к. этот текст левее шапки.",
        ))
        passport_layout.addWidget(labeled_row(
            "Смещение сверху от шапки:", self.passport_top_spin,
            hint="В пикселях, от шапки до текста 'Паспорт #N' — обычно ОТРИЦАТЕЛЬНОЕ число, т.к. этот "
                 "текст ВЫШЕ таблицы результатов.",
        ))
        passport_layout.addWidget(labeled_row(
            "Ширина области:", self.passport_width_spin,
            hint="Ширина захватываемой области текста 'Паспорт #N' в пикселях.",
        ))
        passport_layout.addWidget(labeled_row(
            "Высота области:", self.passport_height_spin,
            hint="Высота захватываемой области текста в пикселях.",
        ))
        layout.addWidget(passport_card)

        scroll_card, scroll_layout = make_card("Прокрутка списка результатов")
        self.max_scroll_spin = self._make_int_spin(s.max_scroll_attempts, 0, 100)
        self.scroll_amount_spin = self._make_int_spin(s.scroll_amount, -5000, 5000)
        scroll_layout.addWidget(labeled_row(
            "Макс. попыток прокрутки:", self.max_scroll_spin,
            hint="Сколько раз пытаться прокрутить список вниз в поисках совпадения, прежде чем сдаться.",
        ))
        scroll_layout.addWidget(labeled_row(
            "Величина прокрутки:", self.scroll_amount_spin,
            hint="Сила одной прокрутки колёсиком мыши (отрицательное число — вниз). Увеличьте по модулю, "
                 "если список длинный и не долистывается до конца за отведённое число попыток.",
        ))
        self.scroll_delay_slider = make_slider(0.0, 2.0, s.scroll_delay, decimals=2, step=0.05)
        scroll_layout.addWidget(slider_field(
            "Пауза после прокрутки", self.scroll_delay_slider, suffix=" с",
            hint="Сколько ждать после прокрутки списка, прежде чем снова читать текст через OCR.",
        ))
        layout.addWidget(scroll_card)

        faction_card, faction_layout = make_card("Область таблицы участников фракции (калибровка под ваш экран)")
        self.faction_name_left_spin = self._make_int_spin(s.faction_name_col_left_offset, -5000, 5000)
        self.faction_name_width_spin = self._make_int_spin(s.faction_name_col_width, 0, 5000)
        self.faction_login_left_spin = self._make_int_spin(s.faction_login_col_left_offset, -5000, 5000)
        self.faction_login_width_spin = self._make_int_spin(s.faction_login_col_width, 0, 5000)
        self.faction_top_spin = self._make_int_spin(s.faction_panel_top_offset, -5000, 5000)
        self.faction_height_spin = self._make_int_spin(s.faction_panel_height, 0, 5000)
        faction_layout.addWidget(labeled_row(
            "Смещение слева до колонки 'Имя':", self.faction_name_left_spin,
            hint="В пикселях, от найденной шапки таблицы участников до левого края колонки 'Имя'. "
                 "Важно НЕ захватывать круглую аватарку/точку 'онлайн' левее текста — OCR иногда "
                 "принимает их за мусорные 'буквы'. Если в списке появляются странные строки-мусор "
                 "(символы, пустые записи) — увеличьте это значение, чтобы сместить область правее аватарки.",
        ))
        faction_layout.addWidget(labeled_row(
            "Ширина колонки 'Имя':", self.faction_name_width_spin,
            hint="Ширина захватываемой области колонки 'Имя' в пикселях.",
        ))
        faction_layout.addWidget(labeled_row(
            "Смещение слева до колонки 'Последний вход':", self.faction_login_left_spin,
            hint="В пикселях, от найденной шапки таблицы участников до левого края колонки 'Последний вход'.",
        ))
        faction_layout.addWidget(labeled_row(
            "Ширина колонки 'Последний вход':", self.faction_login_width_spin,
            hint="Ширина захватываемой области колонки 'Последний вход' в пикселях.",
        ))
        faction_layout.addWidget(labeled_row(
            "Смещение сверху от шапки:", self.faction_top_spin,
            hint="В пикселях, от шапки таблицы до верхнего края первой строки списка.",
        ))
        faction_layout.addWidget(labeled_row(
            "Высота области списка:", self.faction_height_spin,
            hint="Высота захватываемой области (сколько строк списка попадёт в один снимок перед прокруткой). "
                 "Если OCR не видит нужный текст — включите отладочные скриншоты ниже и сверьте, попадает ли текст в рамку.",
        ))
        self.faction_max_scroll_spin = self._make_int_spin(s.faction_max_scroll_attempts, 0, 2000)
        self.faction_scroll_amount_spin = self._make_int_spin(s.faction_scroll_amount, -5000, 5000)
        faction_layout.addWidget(labeled_row(
            "Макс. попыток прокрутки:", self.faction_max_scroll_spin,
            hint="Это ТОЛЬКО страховка от бесконечного цикла — на практике сканирование обычно "
                 "останавливается намного раньше само, как только список дочитан до конца (см. ниже). "
                 "Не нужно занижать это число, пытаясь 'ускорить' сканирование — если список большой, а "
                 "одна прокрутка сдвигает его совсем немного, заниженное значение просто обрежет список, "
                 "не дойдя до конца.",
        ))
        faction_layout.addWidget(labeled_row(
            "Величина прокрутки:", self.faction_scroll_amount_spin,
            hint="Сила одной прокрутки колёсиком мыши (отрицательное число — вниз). Должна быть ЗАМЕТНО "
                 "меньше, чем нужно для одной полной страницы списка — иначе соседние прокрутки почти не "
                 "перекрываются, и часть строк между ними тихо ПРОПУСКАЕТСЯ (не дублируется — просто "
                 "никогда не попадает ни в один снимок). Признак в логе: 'новых участников' почти равно "
                 "'строк распознано' на каждой попытке — если так, уменьшите это значение.",
        ))
        self.faction_scroll_cursor_x_spin = self._make_int_spin(s.faction_scroll_cursor_x_offset, -2000, 2000)
        faction_layout.addWidget(labeled_row(
            "Смещение точки прокрутки вправо:", self.faction_scroll_cursor_x_spin,
            hint="Перед прокруткой колёсиком курсор наводится в центр колонки 'Имя', смещённый вправо на "
                 "столько пикселей — чтобы не попадать на аватарку/иконки. Увеличьте, если прокрутка списка "
                 "не срабатывает или срабатывает не там.",
        ))
        self.faction_scroll_delay_slider = make_slider(0.0, 2.0, s.faction_scroll_delay, decimals=2, step=0.05)
        faction_layout.addWidget(slider_field(
            "Пауза после прокрутки", self.faction_scroll_delay_slider, suffix=" с",
            hint="Сколько ждать после прокрутки списка участников, прежде чем снова читать текст через OCR.",
        ))
        self.faction_no_new_streak_spin = self._make_int_spin(s.faction_stop_after_no_new_streak, 1, 50)
        faction_layout.addWidget(labeled_row(
            "Остановка после стольких прокруток без новых:", self.faction_no_new_streak_spin,
            hint="Если столько прокруток подряд не находят ни одного нового участника (при этом сам "
                 "экран меняется — иначе см. лог 'экран не изменился') — список считается законченным. "
                 "Если сканирование останавливается ЗАМЕТНО раньше конца списка — увеличьте это число: "
                 "соседние прокрутки списка иногда сильно перекрываются, и несколько подряд экранов могут "
                 "не принести ничего нового, даже когда список ещё не дочитан.",
        ))
        layout.addWidget(faction_card)

        faction_total_card, faction_total_layout = make_card(
            "Добор списка по счётчику 'Участников: N' (область над таблицей)"
        )
        faction_total_hint = QLabel(
            "После обычного прохода вниз программа сверяет собранное число с этим счётчиком. Если "
            "собрано меньше — прокручивает список обратно наверх и сканирует заново (собранные ранее "
            "не дублируются), пока не наберёт заявленное число или доп. проход не перестанет находить "
            "новых участников."
        )
        faction_total_hint.setObjectName("muted")
        faction_total_hint.setWordWrap(True)
        faction_total_layout.addWidget(faction_total_hint)
        self.faction_total_left_spin = self._make_int_spin(s.faction_total_left_offset, -5000, 5000)
        self.faction_total_top_spin = self._make_int_spin(s.faction_total_top_offset, -5000, 5000)
        self.faction_total_width_spin = self._make_int_spin(s.faction_total_width, 0, 2000)
        self.faction_total_height_spin = self._make_int_spin(s.faction_total_height, 0, 500)
        faction_total_layout.addWidget(labeled_row(
            "Смещение слева от шапки:", self.faction_total_left_spin,
            hint="В пикселях, от найденной шапки таблицы участников до левого края текста 'Участников: N'.",
        ))
        faction_total_layout.addWidget(labeled_row(
            "Смещение сверху от шапки:", self.faction_total_top_spin,
            hint="В пикселях, от шапки таблицы до текста 'Участников: N' — обычно ОТРИЦАТЕЛЬНОЕ число, "
                 "т.к. этот текст находится ВЫШЕ таблицы, а не ниже.",
        ))
        faction_total_layout.addWidget(labeled_row(
            "Ширина области:", self.faction_total_width_spin,
            hint="Ширина захватываемой области текста 'Участников: N Онлайн: M' в пикселях.",
        ))
        faction_total_layout.addWidget(labeled_row(
            "Высота области:", self.faction_total_height_spin,
            hint="Высота захватываемой области текста в пикселях.",
        ))
        self.faction_extra_passes_spin = self._make_int_spin(s.faction_extra_passes, 0, 20)
        faction_total_layout.addWidget(labeled_row(
            "Макс. доп. проходов наверх-и-заново:", self.faction_extra_passes_spin,
            hint="Сколько раз повторять 'наверх и сканировать заново', пока собранное число не достигнет "
                 "заявленного. 0 — отключить добор (одного прохода вниз всегда будет достаточно, если "
                 "нужно просто быстро, без гарантии полноты).",
        ))
        layout.addWidget(faction_total_card)

        ocr_card, ocr_layout = make_card("OCR")
        tess_row = QHBoxLayout()
        tess_row.addWidget(QLabel("Путь к tesseract.exe:"))
        self.tesseract_edit = QLineEdit(s.tesseract_cmd_override)
        tess_row.addWidget(self.tesseract_edit, 1)
        tess_browse = QPushButton("Обзор…")
        tess_browse.setCursor(Qt.PointingHandCursor)
        tess_browse.clicked.connect(self._browse_tesseract)
        tess_row.addWidget(tess_browse)
        ocr_layout.addLayout(tess_row)
        tess_hint = QLabel(
            "Оставьте пустым для автоопределения — программа сама найдёт версию, встроенную в exe, "
            "либо системную установку. Указывайте вручную, только если автоопределение не сработало."
        )
        tess_hint.setObjectName("muted")
        tess_hint.setWordWrap(True)
        ocr_layout.addWidget(tess_hint)

        self.debug_check = QCheckBox("Сохранять отладочные скриншоты и текст OCR в папку debug/")
        self.debug_check.setChecked(s.debug_save_ocr_images)
        ocr_layout.addWidget(self.debug_check)
        debug_hint = QLabel(
            "Включайте временно для калибровки — покажет, что именно видит программа на экране "
            "и что распознал OCR, если проверка не находит нужный текст."
        )
        debug_hint.setObjectName("muted")
        debug_hint.setWordWrap(True)
        ocr_layout.addWidget(debug_hint)
        layout.addWidget(ocr_card)

        save_row = QHBoxLayout()
        save_row.addStretch()
        save_btn = QPushButton("Сохранить настройки")
        save_btn.setObjectName("primaryButton")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedSize(190, 38)
        save_btn.clicked.connect(self._save_settings)
        save_row.addWidget(save_btn)
        layout.addLayout(save_row)
        layout.addStretch()

    @staticmethod
    def _make_int_spin(value, lo, hi):
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        return spin

    # ------------------------------------------------------------------
    # Обработчики
    # ------------------------------------------------------------------
    def _refresh_processes(self, quiet=False):
        names = automation.list_window_processes()
        current = self.process_combo.currentText()
        self.process_combo.clear()
        self.process_combo.addItems(names)
        self.process_combo.setCurrentText(current)
        if not quiet:
            self._append_log(f"Найдено процессов с видимыми окнами: {len(names)}")

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите входной файл", "", "Текстовые файлы (*.txt);;Все файлы (*.*)")
        if path:
            self.input_file_edit.setText(path)

    def _browse_tesseract(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите tesseract.exe", "", "tesseract.exe;;Все файлы (*.*)")
        if path:
            self.tesseract_edit.setText(path)

    def _append_log(self, msg: str):
        self.log_text.append(msg)

    def _append_result(self, line: str, category: str):
        color = CATEGORY_COLOR.get(category, FG_TEXT)
        safe_line = html.escape(line)
        safe_category = html.escape(category)
        self.output_text.append(f"[<span style='color:{color}; font-weight:bold;'>{safe_category}</span>] {safe_line}")

    def _log_tesseract_status(self):
        cmd = resolve_tesseract_cmd(self.tesseract_edit.text() if hasattr(self, "tesseract_edit") else "")
        if cmd:
            self._append_log(f"Tesseract-OCR найден: {cmd}")
        else:
            self._append_log(
                "ВНИМАНИЕ: Tesseract-OCR не найден (ни встроенный в программу, ни системный). "
                "Проверка результатов работать не будет."
            )

    def _collect_settings(self) -> Settings:
        s = self.settings
        s.mode = next(m for m, rb in self.mode_radios.items() if rb.isChecked())
        s.input_source = INPUT_TEXT if self.rb_input_text.isChecked() else INPUT_FILE
        s.input_file = self.input_file_edit.text().strip()
        s.input_text = self.input_text_edit.toPlainText()
        s.target_process_name = self.process_combo.currentText().strip() or "GTA5.exe"
        s.reactivate_each_entry = self.chk_reactivate.isChecked()
        s.capture_all_monitors = self.chk_multi_monitor.isChecked()
        s.show_overlay = self.chk_overlay.isChecked()
        s.stop_hotkey = self.hotkey_edit.text().strip().lower() or "f3"

        s.confidence = slider_value(self.confidence_slider)
        s.action_delay = slider_value(self.action_delay_slider)
        s.activation_delay = slider_value(self.activation_delay_slider)
        s.results_load_delay = slider_value(self.results_load_delay_slider)
        s.clear_field_backspace_count = int(self.backspace_spin.value())
        s.name_entry_type_interval = slider_value(self.name_type_interval_slider)

        s.results_panel_left_offset = int(self.panel_left_spin.value())
        s.results_panel_top_offset = int(self.panel_top_spin.value())
        s.results_panel_width = int(self.panel_width_spin.value())
        s.results_panel_height = int(self.panel_height_spin.value())

        s.passport_number_left_offset = int(self.passport_left_spin.value())
        s.passport_number_top_offset = int(self.passport_top_spin.value())
        s.passport_number_width = int(self.passport_width_spin.value())
        s.passport_number_height = int(self.passport_height_spin.value())

        s.max_scroll_attempts = int(self.max_scroll_spin.value())
        s.scroll_amount = int(self.scroll_amount_spin.value())
        s.scroll_delay = slider_value(self.scroll_delay_slider)

        s.faction_name_col_left_offset = int(self.faction_name_left_spin.value())
        s.faction_name_col_width = int(self.faction_name_width_spin.value())
        s.faction_login_col_left_offset = int(self.faction_login_left_spin.value())
        s.faction_login_col_width = int(self.faction_login_width_spin.value())
        s.faction_panel_top_offset = int(self.faction_top_spin.value())
        s.faction_panel_height = int(self.faction_height_spin.value())
        s.faction_max_scroll_attempts = int(self.faction_max_scroll_spin.value())
        s.faction_scroll_amount = int(self.faction_scroll_amount_spin.value())
        s.faction_scroll_cursor_x_offset = int(self.faction_scroll_cursor_x_spin.value())
        s.faction_scroll_delay = slider_value(self.faction_scroll_delay_slider)
        s.faction_stop_after_no_new_streak = int(self.faction_no_new_streak_spin.value())

        s.faction_total_left_offset = int(self.faction_total_left_spin.value())
        s.faction_total_top_offset = int(self.faction_total_top_spin.value())
        s.faction_total_width = int(self.faction_total_width_spin.value())
        s.faction_total_height = int(self.faction_total_height_spin.value())
        s.faction_extra_passes = int(self.faction_extra_passes_spin.value())

        s.tesseract_cmd_override = self.tesseract_edit.text().strip()
        s.debug_save_ocr_images = self.debug_check.isChecked()

        s.admin_keywords = [w.strip().lower() for w in self.admin_kw_edit.text().split(",") if w.strip()]
        s.criminal_keywords = [w.strip().lower() for w in self.criminal_kw_edit.text().split(",") if w.strip()]
        return s

    def _save_settings(self):
        settings = self._collect_settings()
        settings.save()
        QMessageBox.information(self, APP_TITLE, "Настройки сохранены.")

    def _on_start(self):
        if self.running:
            return
        settings = self._collect_settings()

        if settings.input_source == INPUT_TEXT:
            if not settings.input_text.strip():
                QMessageBox.critical(self, APP_TITLE, "Вставьте список записей в текстовое поле на странице 'Проверка судимостей'.")
                return
        elif not settings.input_file:
            QMessageBox.critical(self, APP_TITLE, "Укажите входной файл на странице 'Проверка судимостей'.")
            return

        settings.save()

        self.log_text.clear()
        self.output_text.clear()
        self._counts = {"admin": 0, "criminal": 0, "both": 0}
        self.note_label.setText("")
        self.check_detail_label.setText("")

        self.progress.setRange(0, 0)  # indeterminate, пока идёт поиск окна/полей
        self.progress_label.setText("Запуск…")

        if settings.show_overlay:
            self.overlay.set_title("🔍 Проверка судимостей")
            self.overlay.reset(0)
            rect = None
            try:
                rect = automation.find_target_window_rect(settings.target_process_name)
            except Exception:
                rect = None
            self.overlay.position_near(rect)
            self.overlay.show()

        self.stop_event = threading.Event()
        self.running = True
        self._active_stop_button = self.btn_stop
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        self._register_stop_hotkey(settings.stop_hotkey)
        self._start_pulse()

        self.thread = QThread()
        self.worker = AutomationWorker(settings, self.stop_event)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.result.connect(self._on_result)
        self.worker.current.connect(self._on_current_entry)
        self.worker.stats.connect(self._on_stats)
        self.worker.finished.connect(self._on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self._on_error)
        self.worker.failed.connect(self.thread.quit)
        self.thread.start()

    def _on_stop(self):
        if self.running:
            self.stop_event.set()
            self._append_log("Останавливаю после текущей записи…")
            if self._active_stop_button is not None:
                self._active_stop_button.setEnabled(False)

    def closeEvent(self, event):
        if self.running:
            reply = QMessageBox.question(
                self, APP_TITLE, "Обработка ещё выполняется. Остановить и выйти?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self.stop_event.set()
        self._unregister_stop_hotkey()
        self.overlay.hide()
        event.accept()

    # ------------------------------------------------------------------
    # Горячая клавиша аварийной остановки
    # ------------------------------------------------------------------
    def _register_stop_hotkey(self, hotkey: str):
        self._unregister_stop_hotkey()
        if not KEYBOARD_AVAILABLE:
            self._append_log("Модуль 'keyboard' не установлен — горячая клавиша остановки недоступна.")
            return
        if not hotkey:
            return
        try:
            keyboard.add_hotkey(hotkey, self.hotkey_bridge.triggered.emit)
            self._hotkey_registered = hotkey
            self._append_log(f"Горячая клавиша остановки: {hotkey.upper()}")
        except Exception as e:
            self._append_log(f"Не удалось зарегистрировать горячую клавишу '{hotkey}': {e}")

    def _unregister_stop_hotkey(self):
        if self._hotkey_registered and KEYBOARD_AVAILABLE:
            try:
                keyboard.remove_hotkey(self._hotkey_registered)
            except Exception:
                pass
        self._hotkey_registered = None

    def _on_hotkey_stop(self):
        if self.running:
            self.stop_event.set()
            hotkey = self._hotkey_registered or ""
            self._append_log(f"Остановлено горячей клавишей '{hotkey.upper()}'.")
            if self._active_stop_button is not None:
                self._active_stop_button.setEnabled(False)

    # ------------------------------------------------------------------
    # Пульсирующий индикатор статуса, пока идёт обработка
    # ------------------------------------------------------------------
    def _start_pulse(self):
        self.status_text.setText("Выполняется")
        self._pulse_state = True
        self._pulse_timer.start(600)

    def _pulse_tick(self):
        self._pulse_state = not self._pulse_state
        color = ACCENT if self._pulse_state else "#6e5b8a"
        self.status_dot.setStyleSheet(f"color: {color};")

    def _stop_pulse(self):
        self._pulse_timer.stop()
        self.status_dot.setStyleSheet(f"color: {FG_MUTED};")

    def _set_status(self, text, color=None):
        self.status_text.setText(text)
        if color:
            self.status_text.setStyleSheet(f"color: {color};")
            self.status_dot.setStyleSheet(f"color: {color};")

    # ------------------------------------------------------------------
    # Сигналы фонового потока
    # ------------------------------------------------------------------
    def _on_progress(self, cur, total):
        if self.progress.maximum() == 0:
            self.progress.setRange(0, max(total, 1))
        self.progress.setValue(cur)
        self.progress_label.setText(f"{cur}/{total}")

    def _on_current_entry(self, idx, total, label):
        if self.progress.maximum() == 0:
            self.progress.setRange(0, max(total, 1))
        if self.overlay.isVisible():
            self.overlay.set_current(idx, total, label)

    def _on_stats(self, data: dict):
        if self.overlay.isVisible():
            self.overlay.set_stats(data)
        remaining = max(data["total"] - data["idx"], 0)
        self.check_detail_label.setText(
            f"Осталось проверить: {remaining} чел.  ·  Примерное время до конца: "
            f"~{format_seconds(data.get('eta_seconds', 0))}  ·  скорость {data['rate_per_min']:.1f} чел/мин"
        )

    def _on_result(self, line, category):
        self._append_result(line, category)
        key = RESULT_CATEGORY_KEY.get(category)
        if key:
            self._counts[key] += 1

    def _on_finished(self, result: automation.RunResult):
        self.running = False
        self._unregister_stop_hotkey()
        self._stop_pulse()
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_label.setText("Готово")
        self.check_detail_label.setText("")
        self._set_status("Готово", SUCCESS_COLOR)

        note = (
            f"Обработано {result.processed} из {result.total}.  "
            f"АК: {self._counts['admin']}   УК: {self._counts['criminal']}   УК + АК: {self._counts['both']}"
        )
        if result.avg_time:
            note += (
                f"\nВремя: сред. {result.avg_time:.1f}с/чел, мин {result.min_time:.1f}с, "
                f"макс {result.max_time:.1f}с  ·  {result.rate_per_min:.1f} чел/мин "
                f"(всего {format_seconds(result.total_time)})"
            )
        if result.stopped_early:
            note += "\nОстановлено пользователем до завершения."
        self.note_label.setText(note)
        self._append_log("\n" + note)

        if self.overlay.isVisible():
            self.overlay.set_finished("Остановлено" if result.stopped_early else "Готово ✓")
            QTimer.singleShot(5000, self.overlay.hide)

        title = "Проверка остановлена" if result.stopped_early else "Проверка завершена"
        self._notify(title, note.replace("  ", " "))

    def _on_error(self, message: str):
        self.running = False
        self._unregister_stop_hotkey()
        self._stop_pulse()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_label.setText("Ошибка")
        self.check_detail_label.setText("")
        self._set_status("Ошибка", ERROR_COLOR)
        self.note_label.setText(f"Прогон завершился ошибкой: {message}")
        self._append_log(f"\nОШИБКА: {message}")
        if self.overlay.isVisible():
            self.overlay.set_finished("Ошибка ✕")
            QTimer.singleShot(5000, self.overlay.hide)
        self._notify("Ошибка проверки", message.splitlines()[0] if message else "Неизвестная ошибка", warning=True)
        QMessageBox.critical(self, APP_TITLE, message)

    # ------------------------------------------------------------------
    # Страница "Фракция" — сбор списка участников и отбор неактивных
    # ------------------------------------------------------------------
    def _on_faction_collect_start(self):
        self._start_faction_task("collect")

    def _on_faction_inactive_start(self):
        self._start_faction_task("inactive")

    def _start_faction_task(self, mode: str):
        if self.running:
            QMessageBox.warning(
                self, APP_TITLE,
                "Уже выполняется другая операция — дождитесь её завершения или нажмите 'Стоп'.",
            )
            return
        settings = self._collect_settings()
        settings.save()

        self._faction_mode = mode
        if mode == "collect":
            self.faction_members_text.clear()
            self.faction_members_label.setText("Выполняется…")
        else:
            self.faction_inactive_text.clear()
            self.faction_inactive_label.setText("Выполняется…")

        self.faction_progress_label.setText("Запуск…")

        if settings.show_overlay:
            self.overlay.set_title("🏛 Парсинг фракции")
            self.overlay.reset_faction()
            rect = None
            try:
                rect = automation.find_target_window_rect(settings.target_process_name)
            except Exception:
                rect = None
            self.overlay.position_near(rect)
            self.overlay.show()

        self.stop_event = threading.Event()
        self.running = True
        self._active_stop_button = self.btn_faction_stop
        self.btn_faction_collect.setEnabled(False)
        self.btn_faction_inactive.setEnabled(False)
        self.btn_faction_stop.setEnabled(True)

        self._register_stop_hotkey(settings.stop_hotkey)
        self._start_pulse()

        self.thread = QThread()
        self.worker = FactionWorker(settings, self.stop_event)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.count.connect(self._on_faction_count)
        self.worker.finished.connect(self._on_faction_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self._on_faction_failed)
        self.worker.failed.connect(self.thread.quit)
        self.thread.start()

    def _on_faction_count(self, collected: int, attempt: int):
        self.faction_progress_label.setText(f"Собрано: {collected}")
        if self.overlay.isVisible():
            self.overlay.set_faction_progress(collected)

    @staticmethod
    def _faction_total_suffix(result: "automation.FactionCollectResult") -> str:
        if result.expected_total is None:
            return ""
        if len(result.members) >= result.expected_total:
            return f" из {result.expected_total} заявленных ✓"
        return f" из {result.expected_total} заявленных"

    def _render_faction_members(self, result: "automation.FactionCollectResult"):
        lines = [m["name"] for m in result.members]
        self.faction_members_text.setPlainText("\n".join(lines))
        note = f"Собрано участников: {len(result.members)}{self._faction_total_suffix(result)}"
        if result.stopped_early:
            note += "  ·  остановлено пользователем"
        self.faction_members_label.setText(note)

    def _render_faction_inactive(self, result: "automation.FactionCollectResult"):
        cutoff = self.faction_cutoff_date.date().toPython()
        inactive = automation.filter_inactive_members(result.members, cutoff)
        lines = [f"{m['name']} — {m['last_login_raw'] or '?'}" for m in inactive]
        self.faction_inactive_text.setPlainText("\n".join(lines))
        note = (
            f"Найдено кандидатов на исключение: {len(inactive)} из {len(result.members)} собранных"
            f"{self._faction_total_suffix(result)} (не заходили с {cutoff.strftime('%d.%m.%Y')})"
        )
        if result.stopped_early:
            note += "  ·  остановлено пользователем, список неполный"
        self.faction_inactive_label.setText(note)

    def _on_faction_finished(self, result: "automation.FactionCollectResult"):
        self.running = False
        self._unregister_stop_hotkey()
        self._stop_pulse()
        self.btn_faction_collect.setEnabled(True)
        self.btn_faction_inactive.setEnabled(True)
        self.btn_faction_stop.setEnabled(False)
        self.faction_progress_label.setText("Готово")
        self._set_status("Готово", SUCCESS_COLOR)

        if self._faction_mode == "collect":
            self._render_faction_members(result)
        else:
            self._render_faction_inactive(result)

        if self.overlay.isVisible():
            self.overlay.set_finished("Остановлено" if result.stopped_early else "Готово ✓")
            QTimer.singleShot(5000, self.overlay.hide)

        title = "Сбор списка фракции остановлен" if result.stopped_early else "Сбор списка фракции завершён"
        self._notify(title, f"Собрано участников: {len(result.members)}")

    def _on_faction_failed(self, message: str):
        self.running = False
        self._unregister_stop_hotkey()
        self._stop_pulse()
        self.btn_faction_collect.setEnabled(True)
        self.btn_faction_inactive.setEnabled(True)
        self.btn_faction_stop.setEnabled(False)
        self.faction_progress_label.setText("Ошибка")
        self._set_status("Ошибка", ERROR_COLOR)
        short_message = message.splitlines()[0] if message else "Неизвестная ошибка"
        if self._faction_mode == "collect":
            self.faction_members_label.setText(f"Ошибка: {short_message}")
        else:
            self.faction_inactive_label.setText(f"Ошибка: {short_message}")
        self._append_log(f"\nОШИБКА: {message}")
        if self.overlay.isVisible():
            self.overlay.set_finished("Ошибка ✕")
            QTimer.singleShot(5000, self.overlay.hide)
        self._notify("Ошибка парсинга фракции", short_message, warning=True)
        QMessageBox.critical(self, APP_TITLE, message)

    def _notify(self, title: str, message: str, warning: bool = False):
        """Системное уведомление о завершении проверки (трей), чтобы было
        видно даже если окно программы свёрнуто. Трей-иконка включается
        только на время показа уведомления, чтобы не висеть постоянно."""
        if self.tray is None:
            return
        try:
            icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
            self.tray.setVisible(True)
            self.tray.showMessage(title, message, icon, 6000)
            QTimer.singleShot(6500, lambda: self.tray.setVisible(False))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Проверка обновлений (GitHub Releases API, в фоновом потоке)
    # ------------------------------------------------------------------
    def _start_update_check(self):
        def worker():
            updater.check_for_update(lambda v, u: self.update_bridge.found.emit(v or "", u or ""))

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_banner(self, version, url):
        if not version:
            return
        self._update_label.setText(f"🔔 Доступна новая версия {version} (у вас {updater.APP_VERSION})")
        try:
            self._update_link_btn.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._update_link_btn.clicked.connect(lambda: webbrowser.open(url))
        self.update_banner.setVisible(True)


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # база без нативных Windows-виджетов — QSS ложится предсказуемо
    app.setStyleSheet(STYLE_SHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
