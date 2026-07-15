# -*- coding: utf-8 -*-
"""
Поиск шаблона (картинки) на скриншоте без OpenCV — на чистом numpy.

Раньше поиск элементов на экране (поле ввода, кнопка, шапка таблицы)
делал pyautogui/pyscreeze через cv2.matchTemplate(..., TM_CCOEFF_NORMED).
OpenCV — это ~85 МБ веса в собранном exe ради одной функции, поэтому
здесь она переписана на numpy: та же нормализованная кросс-корреляция
(zero-mean, normalized), только вычисленная через БПФ (для скорости) и
интегральное изображение (для скользящего среднего/дисперсии) вместо
готовой функции OpenCV.

Результат математически эквивалентен cv2.matchTemplate с
TM_CCOEFF_NORMED (см. tests/сравнение в момент разработки) — значения
"confidence", подобранные раньше под OpenCV (обычно 0.7-0.9), работают
так же.
"""

from typing import NamedTuple

import numpy as np
from PIL import Image


class Box(NamedTuple):
    left: int
    top: int
    width: int
    height: int


def _to_gray_f64(img: Image.Image) -> np.ndarray:
    """Преобразует PIL-изображение в grayscale float64-массив тем же
    способом (коэффициенты BT.601), что и OpenCV/pyscreeze. Именно
    float64, не float32: локальная дисперсия считается как разность двух
    больших близких чисел (сумма квадратов минус квадрат суммы) через
    интегральное изображение на весь скриншот — на float32 это давало
    катастрофическую потерю точности на больших (мультимониторных)
    кадрах и оценки вида 4.17 вместо честных [-1, 1]."""
    return np.asarray(img.convert("L"), dtype=np.float64)


def _load_template_gray(path) -> np.ndarray:
    with Image.open(path) as img:
        return _to_gray_f64(img)


def _integral_image(a: np.ndarray) -> np.ndarray:
    """Интегральное изображение (summed-area table) с нулевой рамкой
    сверху/слева — удобно для O(1)-вычисления суммы в любом окне."""
    s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    np.cumsum(np.cumsum(a, axis=0), axis=1, out=s[1:, 1:])
    return s


def _window_sums(integral: np.ndarray, h: int, w: int) -> np.ndarray:
    """Сумма значений в каждом окне h x w по интегральному изображению."""
    return integral[h:, w:] - integral[:-h, w:] - integral[h:, :-w] + integral[:-h, :-w]


def _fft_size(n: int) -> int:
    """Ближайшее удобное для БПФ число >= n (гладкое по 2/3/5), чтобы не
    считать быстрое преобразование Фурье на "неудобном" простом размере."""
    n = max(int(n), 1)
    while True:
        m = n
        for p in (2, 3, 5):
            while m % p == 0:
                m //= p
        if m == 1:
            return n
        n += 1


def match_template(haystack_gray: np.ndarray, needle_gray: np.ndarray) -> np.ndarray:
    """Нормализованная кросс-корреляция (эквивалент cv2.TM_CCOEFF_NORMED).
    Возвращает 2D-массив оценок совпадения размером
    (H-h+1) x (W-w+1), где [0, 1] (на практике обычно [-1, 1])."""
    H, W = haystack_gray.shape
    h, w = needle_gray.shape
    if H < h or W < w:
        raise ValueError("Шаблон больше области поиска")

    out_h, out_w = H - h + 1, W - w + 1

    needle_mean = needle_gray.mean()
    needle_zero = needle_gray - needle_mean
    needle_energy = float(np.sum(needle_zero * needle_zero))

    # --- числитель: sum((I_patch - mean(I_patch)) * (T - mean(T))) ---
    # т.к. needle_zero имеет нулевое среднее, это равно линейной кросс-
    # корреляции haystack с needle_zero (без учёта mean(I_patch)),
    # которую считаем через БПФ (быстрее, чем прямой перебор окон).
    fh, fw = _fft_size(H + h - 1), _fft_size(W + w - 1)

    kernel = np.zeros((fh, fw), dtype=np.float64)
    kernel[:h, :w] = needle_zero[::-1, ::-1]  # флип для корреляции через свёртку

    fft_haystack = np.fft.rfft2(haystack_gray, s=(fh, fw))
    fft_kernel = np.fft.rfft2(kernel, s=(fh, fw))
    full_conv = np.fft.irfft2(fft_haystack * fft_kernel, s=(fh, fw))

    numerator = full_conv[h - 1 : h - 1 + out_h, w - 1 : w - 1 + out_w]

    # --- знаменатель: sqrt(sum((I_patch-mean_I)^2) * sum((T-mean_T)^2)) ---
    integral = _integral_image(haystack_gray)
    integral_sq = _integral_image(haystack_gray * haystack_gray)
    win_sum = _window_sums(integral, h, w)
    win_sum_sq = _window_sums(integral_sq, h, w)
    local_energy = win_sum_sq - (win_sum * win_sum) / (h * w)
    np.clip(local_energy, 0, None, out=local_energy)

    denom = np.sqrt(local_energy * needle_energy)
    # Порог знаменателя — относительный (от энергии шаблона), а не
    # абсолютный: абсолютный epsilon вида 1e-5 ничего не значит для
    # изображения с диапазоном яркости 0-255 и был источником деления на
    # почти ноль (и оценок вида 4.17) на плоских/однотонных участках.
    denom_floor = max(np.sqrt(needle_energy) * 1e-3, 1e-6)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(denom > denom_floor, numerator / denom, 0.0)

    # Нормализованная кросс-корреляция математически не может выходить
    # за [-1, 1] — если вышла, это остаточная погрешность вычислений, а
    # не реальное совпадение; обрезаем как страховку.
    np.clip(result, -1.0, 1.0, out=result)

    return result


def _screenshot_to_gray(image) -> np.ndarray:
    if isinstance(image, np.ndarray):
        return image.astype(np.float64)
    return _to_gray_f64(image)


def find_best(template_path, haystack_image, confidence: float):
    """Как locate_all_on_image, но всегда возвращает лучшее совпадение и
    его оценку — даже если она ниже confidence. Нужно для диагностики
    ('кнопка не найдена, лучшее совпадение 0.62 из требуемых 0.80').
    Возвращает (matched: bool, score: float, box: Box | None)."""
    needle_gray = _load_template_gray(template_path)
    haystack_gray = _screenshot_to_gray(haystack_image)

    if haystack_gray.shape[0] < needle_gray.shape[0] or haystack_gray.shape[1] < needle_gray.shape[1]:
        return False, 0.0, None

    scores = match_template(haystack_gray, needle_gray)
    h, w = needle_gray.shape
    idx = int(np.argmax(scores))
    y, x = np.unravel_index(idx, scores.shape)
    score = float(scores[y, x])
    box = Box(int(x), int(y), w, h)
    return score >= confidence, score, box


