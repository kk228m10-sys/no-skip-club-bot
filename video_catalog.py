"""
Каталог видео упражнений со sportkuznica.com.

Данные лежат в data/sportkuznica_exercises.json (собирается скриптом
scripts/scrape_sportkuznica.py). Когда появятся твои планы тренировок —
сопоставление имени упражнения из плана с видео будет через find_video().
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
_CATALOG_NAME = "sportkuznica_exercises.json"

# Fallback: если data/ не попала на хостинг — качаем с публичного GitHub.
_CATALOG_FALLBACK_URL = os.getenv(
    "VIDEO_CATALOG_URL",
    "https://raw.githubusercontent.com/kk228m10-sys/no-skip-club-bot/main/data/sportkuznica_exercises.json",
)


def _candidate_paths() -> list[Path]:
    """Где может лежать JSON на ПК / Docker / Bothost."""
    env = (os.getenv("VIDEO_CATALOG_PATH") or "").strip()
    paths: list[Path] = []
    if env:
        paths.append(Path(env))
    paths.extend(
        [
            _BASE_DIR / "data" / _CATALOG_NAME,
            Path.cwd() / "data" / _CATALOG_NAME,
            Path("/app/data") / _CATALOG_NAME,
            Path("/data") / _CATALOG_NAME,
        ]
    )
    # unique preserve order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def resolve_data_path() -> Path | None:
    for p in _candidate_paths():
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


DATA_PATH = _BASE_DIR / "data" / _CATALOG_NAME  # default (may be overridden at load)

# Маппинг тегов сайта → place бота
PLACE_MAP = {
    "зал": "gym",
    "дом": "home",
    "улица": "street",
}

LEVEL_MAP = {
    "начальный уровень": "beginner",
    "базовый": "beginner",
    "продвинутый": "intermediate",
    "профессионал": "advanced",
}

_cache: list[dict] | None = None
_by_id: dict[str, dict] | None = None


def _norm(text: str) -> str:
    """Нормализация для поиска: lower, ё→е, без пунктуации."""
    if not text:
        return ""
    text = text.lower().replace("ё", "е")
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _ensure_catalog_file() -> Path | None:
    """Находит локальный JSON или скачивает fallback с GitHub."""
    global DATA_PATH
    found = resolve_data_path()
    if found is not None:
        DATA_PATH = found
        return found

    # Сохраняем рядом с кодом (или в /tmp, если data/ read-only)
    targets = [
        _BASE_DIR / "data" / _CATALOG_NAME,
        Path("/tmp") / _CATALOG_NAME,
        Path.cwd() / "data" / _CATALOG_NAME,
    ]
    url = _CATALOG_FALLBACK_URL
    if not url:
        logger.warning("Каталог видео не найден локально и VIDEO_CATALOG_URL пуст")
        return None

    last_err: Exception | None = None
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Каталог видео: скачиваю fallback %s → %s", url, target)
            req = urllib.request.Request(url, headers={"User-Agent": "NoSkipClubBot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if not data or len(data) < 100:
                raise RuntimeError(f"Пустой ответ fallback ({len(data)} bytes)")
            target.write_bytes(data)
            DATA_PATH = target
            logger.info("Каталог видео сохранён: %s (%s bytes)", target, len(data))
            return target
        except Exception as e:
            last_err = e
            logger.warning("Не удалось сохранить каталог в %s: %s", target, e)

    logger.error("Не удалось получить каталог видео: %s", last_err)
    return None


def load_catalog(force: bool = False) -> list[dict]:
    global _cache, _by_id, DATA_PATH
    if _cache is not None and not force:
        return _cache

    path = _ensure_catalog_file()
    if path is None:
        logger.warning(
            "Каталог видео пуст: файл не найден. Искали: %s",
            ", ".join(str(p) for p in _candidate_paths()),
        )
        _cache = []
        _by_id = {}
        return _cache

    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.error("Не удалось прочитать каталог %s: %s", path, e)
        _cache = []
        _by_id = {}
        return _cache

    if not isinstance(raw, list):
        logger.error("Каталог %s: ожидался JSON-массив, получено %s", path, type(raw))
        _cache = []
        _by_id = {}
        return _cache

    items = []
    by_id = {}
    for row in raw:
        if not isinstance(row, dict):
            continue
        if row.get("error") or not row.get("id"):
            continue
        item = dict(row)
        item["_norm_title"] = _norm(item.get("title") or "")
        # нормализованные place/level
        places = []
        for p in item.get("place") or []:
            key = PLACE_MAP.get(_norm(p))
            if key and key not in places:
                places.append(key)
        item["_places"] = places

        levels = []
        for lv in item.get("difficulty") or []:
            key = LEVEL_MAP.get(_norm(lv))
            if key and key not in levels:
                levels.append(key)
        item["_levels"] = levels

        item["video_url"] = (
            item.get("youtube_url")
            or item.get("iframe_src")
            or item.get("mp4")
            or item.get("video_src")
            or item.get("vk_url")
        )
        items.append(item)
        by_id[str(item["id"])] = item

    _cache = items
    _by_id = by_id
    logger.info("Каталог видео загружен: %s записей из %s", len(items), path)
    return _cache


def get_by_id(item_id: str | int) -> dict | None:
    load_catalog()
    return (_by_id or {}).get(str(item_id))


def catalog_stats() -> dict:
    items = load_catalog()
    with_video = sum(1 for i in items if i.get("video_url"))
    return {"total": len(items), "with_video": with_video, "path": str(DATA_PATH)}


# Синонимы / упрощения названий из планов → ключи поиска
_ALIASES = {
    "отжимания классические": "отжимания от пола",
    "отжимания с колен или от стены": "отжимания от пола",
    "отжимания с колен": "отжимания от пола",
    "отжимания от стены": "отжимания от пола",
    "отжимания с хлопком": "отжимания от пола",
    "приседания с собственным весом": "воздушные приседания",
    "приседания с паузой": "воздушные приседания",
    "воздушный присед": "воздушные приседания",
    "берпи": "бурпи берпи",
    "бёрпи": "бурпи берпи",
    "планка": "планка и ее разновидности",
    "планка с касанием плеча": "планка и ее разновидности",
    "ягодичный мостик": "мостик на двух ногах",
    "выпады на месте": "выпады на месте",
    "болгарские выпады": "болгарские приседания",
    "болгарские выпады (нога на возвышении)": "болгарские приседания",
    "подтягивания": "строгие подтягивания на турнике",
    "становая": "становая тяга",
    "махи гирей": "махи гирей",
    "гоблет": "приседания с гирей у груди",
    "приседания со штангой": "приседания со штангой",
    "жим лежа": "жим штанги лежа",
    "тяга в наклоне": "тяга штанги к поясу в наклоне",
    "румынская тяга": "мертвая тяга",
    "жим гантелей сидя": "жим гантелей сидя",
    "подъемы на носки": "подъемы на носки",
    "пистолетик": "пистолетик приседания на одной ноге",
    "пистолетик (присед на одной ноге)": "пистолетик приседания на одной ноге",
}


def search(query: str, limit: int = 10, place: str | None = None) -> list[dict]:
    """Поиск по названию. place: home / gym / street / None."""
    items = load_catalog()
    raw_q = _norm(query)
    if not raw_q:
        return []

    # применяем алиасы
    q = _ALIASES.get(raw_q, raw_q)
    for alias, target in _ALIASES.items():
        if alias in raw_q:
            q = target
            break

    tokens = [t for t in q.split() if len(t) > 1]
    scored = []
    for item in items:
        if place and item.get("_places") and place not in item["_places"]:
            continue

        title = item.get("_norm_title") or ""
        if not title:
            continue

        score = 0
        if q == title or raw_q == title:
            score = 1000
        elif title.startswith(q) or title.startswith(raw_q):
            score = 800 - min(len(title), 80)
        elif q in title or raw_q in title:
            # короткие точные вхождения лучше длинных "сборок"
            score = 600 - min(len(title), 100)
        elif tokens and all(t in title for t in tokens):
            score = 300 + sum(25 for t in tokens if t in title) - min(len(title), 50)
        else:
            hits = sum(1 for t in tokens if t in title)
            if hits == 0 or hits < max(1, len(tokens) // 2):
                continue
            score = hits * 40 - min(len(title), 40)

        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], len(x[1].get("_norm_title") or ""), x[1].get("title") or ""))
    return [i for _, i in scored[:limit]]


def find_video(exercise_name: str, place: str | None = None) -> dict | None:
    """Лучшее совпадение видео для названия упражнения из плана."""
    results = search(exercise_name, limit=5, place=place)
    if results:
        return results[0]
    if place:
        results = search(exercise_name, limit=5, place=None)
        if results:
            return results[0]
    return None


def format_video_card(item: dict) -> str:
    title = item.get("title") or "Упражнение"
    desc = (item.get("description") or "").strip()
    if len(desc) > 500:
        desc = desc[:500].rsplit(" ", 1)[0] + "…"

    lines = [f"🎬 <b>{title}</b>"]
    if desc:
        lines.append("")
        lines.append(desc)

    places = item.get("place") or []
    equip = item.get("equipment") or []
    if places:
        lines.append(f"\n📍 Место: {', '.join(places[:5])}")
    if equip:
        lines.append(f"🏋️ Снаряд: {', '.join(equip[:6])}")

    url = item.get("video_url") or item.get("url")
    if url:
        lines.append(f"\n▶️ Видео: {url}")
    if item.get("url") and item.get("url") != url:
        lines.append(f"📄 Страница: {item['url']}")

    return "\n".join(lines)


def list_for_place(place: str, limit: int = 30) -> list[dict]:
    items = load_catalog()
    matched = [i for i in items if place in (i.get("_places") or [])]
    # если мало — добавим без тега места
    if len(matched) < 10:
        others = [i for i in items if i not in matched]
        matched.extend(others[: max(0, limit - len(matched))])
    return matched[:limit]


def bind_library_videos(library: dict) -> int:
    """Проставляет video_url / video_title в EXERCISE_LIBRARY (на месте).
    Возвращает сколько упражнений получили ссылку."""
    load_catalog()
    bound = 0
    for place, levels in library.items():
        if not isinstance(levels, dict):
            continue
        for _level, exercises in levels.items():
            if not isinstance(exercises, list):
                continue
            for ex in exercises:
                if not isinstance(ex, dict) or not ex.get("name"):
                    continue
                if ex.get("video_url"):
                    bound += 1
                    continue
                video = find_video(ex["name"], place=place)
                if video and video.get("video_url"):
                    ex["video_url"] = video["video_url"]
                    ex["video_title"] = video.get("title")
                    ex["video_id"] = video.get("id")
                    bound += 1
    return bound
