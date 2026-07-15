# -*- coding: utf-8 -*-
"""
Проверка обновлений через GitHub Releases API. Никакого автообновления —
только уведомление в интерфейсе со ссылкой на скачивание, пользователь
сам решает, когда обновляться (exe не может сам себя подменить на
Windows, а лаунчер-обёртка ради этого — избыточное усложнение для
такого маленького инструмента).
"""

import json
import re
import urllib.request
from typing import Callable, Optional

APP_VERSION = "1.0"
GITHUB_REPO = "marensovich/GTA5RPUtil"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

_REQUEST_TIMEOUT = 5


def _parse_version(text: str):
    """'v1.2.3-beta' -> (1, 2, 3). Нечисловые хвосты отбрасываются;
    некорректная строка даёт (0,) (никогда не считается "новее")."""
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not match:
        return (0,)
    return tuple(int(g) if g is not None else 0 for g in match.groups())


def is_newer(remote_version: str, local_version: str = APP_VERSION) -> bool:
    return _parse_version(remote_version) > _parse_version(local_version)


def check_for_update(on_result: Callable[[Optional[str], Optional[str]], None]):
    """Синхронно стучится в GitHub Releases API (вызывайте из фонового
    потока, не из основного потока Tkinter). on_result(version, url)
    вызывается с (None, None), если обновлений нет / проверка не
    удалась, либо с (тег_версии, ссылка_на_релиз), если найдена более
    новая версия. on_result сам должен быть потокобезопасным (например,
    класть сообщение в очередь, а не трогать виджеты напрямую)."""
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GTA5RPUtil"},
        )
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name") or "").strip()
        url = str(data.get("html_url") or GITHUB_RELEASES_URL).strip()
        if tag and is_newer(tag, APP_VERSION):
            on_result(tag, url)
        else:
            on_result(None, None)
    except Exception:
        # Нет интернета, репозиторий приватный/ещё без релизов, лимит
        # запросов GitHub и т.п. — не мешаем пользователю ошибками,
        # просто молча пропускаем проверку.
        on_result(None, None)
