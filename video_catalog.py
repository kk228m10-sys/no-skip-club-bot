"""
Каталог видео упражнений со sportkuznica.com.

Данные лежат в data/sportkuznica_exercises.json (собирается скриптом
scripts/scrape_sportkuznica.py). Когда появятся твои планы тренировок —
сопоставление имени упражнения из плана с видео будет через find_video().
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "sportkuznica_exercises.json"

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


def load_catalog(force: bool = False) -> list[dict]:
    global _cache, _by_id
    if _cache is not None and not force:
        return _cache

    if not DATA_PATH.exists():
        _cache = []
        _by_id = {}
        return _cache

    with open(DATA_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    items = []
    by_id = {}
    for row in raw:
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
