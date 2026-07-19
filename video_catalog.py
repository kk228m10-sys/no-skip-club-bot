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

# Минимальный «здоровый» каталог. Меньше — считаем файл битым/устаревшим
# и пробуем другой путь / GitHub fallback (чтобы не «схлопывался» после рестарта).
_MIN_CATALOG_ITEMS = int(os.getenv("VIDEO_CATALOG_MIN_ITEMS") or "100")

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


def _peek_catalog_count(path: Path) -> int | None:
    """Сколько валидных записей в JSON (None = не удалось прочитать)."""
    try:
        if not path.is_file() or path.stat().st_size < 100:
            return None
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            return None
        return sum(1 for row in raw if isinstance(row, dict) and row.get("id") and not row.get("error"))
    except Exception:
        return None


def resolve_data_path() -> Path | None:
    """Выбираем самый полный валидный каталог среди кандидатов.

    Раньше брался первый существующий файл — на хостинге пустой/старый
    файл на Volume (/data) мог перебить полный data/ из деплоя.
    """
    best: Path | None = None
    best_count = -1
    for p in _candidate_paths():
        count = _peek_catalog_count(p)
        if count is None:
            continue
        if count < _MIN_CATALOG_ITEMS:
            logger.warning(
                "Каталог %s слишком мал (%s < %s) — пропускаю",
                p,
                count,
                _MIN_CATALOG_ITEMS,
            )
            continue
        if count > best_count:
            best = p
            best_count = count
    return best


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


def _validate_catalog_bytes(data: bytes) -> int:
    """Проверяет, что bytes — JSON-массив достаточного размера. Возвращает count."""
    if not data or len(data) < 100:
        raise RuntimeError(f"Пустой ответ fallback ({len(data) if data else 0} bytes)")
    raw = json.loads(data.decode("utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError(f"Fallback: ожидался JSON-массив, получено {type(raw)}")
    count = sum(1 for row in raw if isinstance(row, dict) and row.get("id") and not row.get("error"))
    if count < _MIN_CATALOG_ITEMS:
        raise RuntimeError(f"Fallback каталог слишком мал: {count} < {_MIN_CATALOG_ITEMS}")
    return count


def _ensure_catalog_file() -> Path | None:
    """Находит локальный JSON или скачивает fallback с GitHub."""
    global DATA_PATH
    found = resolve_data_path()
    if found is not None:
        DATA_PATH = found
        return found

    # Сохраняем рядом с кодом (или в /tmp, если data/ read-only).
    # /tmp предпочтительнее Volume /data — volume часто переживает редеплой
    # со старым/пустым файлом и снова «ломал» каталог.
    targets = [
        _BASE_DIR / "data" / _CATALOG_NAME,
        Path.cwd() / "data" / _CATALOG_NAME,
        Path("/tmp") / _CATALOG_NAME,
    ]
    url = _CATALOG_FALLBACK_URL
    if not url:
        logger.warning("Каталог видео не найден локально и VIDEO_CATALOG_URL пуст")
        return None

    last_err: Exception | None = None
    try:
        logger.info("Каталог видео: скачиваю fallback %s", url)
        req = urllib.request.Request(url, headers={"User-Agent": "NoSkipClubBot/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        count = _validate_catalog_bytes(data)
    except Exception as e:
        logger.error("Не удалось скачать/проверить fallback каталог: %s", e)
        return None

    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            DATA_PATH = target
            logger.info(
                "Каталог видео сохранён: %s (%s bytes, %s items)",
                target,
                len(data),
                count,
            )
            return target
        except Exception as e:
            last_err = e
            logger.warning("Не удалось сохранить каталог в %s: %s", target, e)

    logger.error("Не удалось сохранить каталог видео: %s", last_err)
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
    "отжимания с хлопком перед грудью": "отжимания от пола",
    "отжимания с ногами на возвышении": "отжимания от пола",
    "отжимания с широкой постановкой рук": "отжимания от пола",
    "отжимания с ногами на скамье": "отжимания от пола",
    "приседания с собственным весом": "воздушные приседания",
    "приседания с паузой": "воздушные приседания",
    "воздушный присед": "воздушные приседания",
    "приседания с выпрыгиванием вверх": "приседания с выпрыгиванием",
    "приседания с выпрыгиванием на максимальную высоту": "приседания с выпрыгиванием",
    "приседания сумо с выпрыгиванием": "приседания плие",
    "берпи": "бурпи берпи",
    "бёрпи": "бурпи берпи",
    "планка": "планка и ее разновидности",
    "планка с касанием плеча": "планка и ее разновидности",
    "планка с касанием плеч": "планка и ее разновидности",
    "планка с быстрым касанием плеч": "планка и ее разновидности",
    "планка с поочередным подъемом руки и ноги": "планка и ее разновидности",
    "планка с попеременным подъемом руки и ноги": "планка и ее разновидности",
    "планка обычная и боковая": "планка и ее разновидности",
    "ягодичный мостик": "мостик на двух ногах",
    "ягодичный мост": "мостик на двух ногах",
    "ягодичный мост со штангой": "мостик на двух ногах",
    "ягодичный мостик на одной ноге": "мостик на одной ноге",
    "подъем таза лежа": "мостик на двух ногах",
    "выпады на месте": "выпады на месте",
    "выпады со сменой ног в прыжке": "выпады",
    "выпады с прыжком со сменой ног": "выпады",
    "выпады с поворотом корпуса": "выпады",
    "болгарские выпады": "болгарские приседания",
    "болгарские выпады (нога на возвышении)": "болгарские приседания",
    "болгарские выпады с гантелями": "болгарские приседания",
    "подтягивания": "строгие подтягивания на турнике",
    "подтягивания широким хватом": "подтягивания широким хватом",
    "становая": "становая тяга",
    "махи гирей": "махи гирей",
    "махи гантелями в стороны": "махи гантелями",
    "гоблет": "приседания с гирей у груди",
    "приседания со штангой": "приседания со штангой",
    "жим лежа": "жим штанги лежа",
    "тяга в наклоне": "тяга штанги к поясу в наклоне",
    "тяга гантели одной рукой в упоре на скамье": "тяга гантели в наклоне",
    "тяга горизонтальная в тренажере": "тяга горизонтального блока",
    "румынская тяга": "мертвая тяга",
    "румынская тяга со штангой": "мертвая тяга",
    "румынская тяга на одной ноге": "мертвая тяга",
    "румынская тяга на одной ноге с гантелями": "мертвая тяга",
    "жим гантелей сидя": "жим гантелей сидя",
    "подъемы на носки": "подъемы на носки",
    "подъем штанги на бицепс стоя": "подъем штанги на бицепс",
    "пистолетик": "пистолетик приседания на одной ноге",
    "пистолетик (присед на одной ноге)": "пистолетик приседания на одной ноге",
    "прыжки на месте с высоким подниманием коленей": "бег сгибая ноги",
    "прыжки на месте с высоким подъемом колен": "бег сгибая ноги",
    "высокое поднимание колен": "бег сгибая ноги",
    "прыжки в длину с места": "прыжки на тумбу",
    "запрыгивания на возвышение": "прыжки на тумбу",
    "быстрые запрыгивания на низкую опору": "прыжки на тумбу",
    "подъем на низкую коробку": "зашагивания на тумбу",
    "подъем на низкую коробку с двух ног": "зашагивания на тумбу",
    "степ ап": "зашагивания на тумбу",
    "степ-ап": "зашагивания на тумбу",
    "степ-ап на низкой опоре": "зашагивания на тумбу",
    "скручивания с быстрым подъемом корпуса": "лучшие упражнения для пресса",
    "скручивания с быстрым подъемом": "лучшие упражнения для пресса",
    "скручивания на римском стуле с поворотом": "лучшие упражнения для пресса",
    "скручивания лежа на спине": "лучшие упражнения для пресса",
    "скручивания на верхнем блоке": "лучшие упражнения для пресса",
    "скручивания с блином на груди": "лучшие упражнения для пресса",
    "скручивания на пресс в быстром темпе": "лучшие упражнения для пресса",
    "взрывные скручивания": "лучшие упражнения для пресса",
    "альпинист": "планка",
    "скакалка в высоком темпе": "прыжки на скакалке",
    "кардио на дорожке или велотренажере": "бег средний темп",
    "спринты на беговой дорожке": "бег быстрый темп",
    "ходьба на месте или на дорожке": "бег медленный темп",
    "бег с ускорением": "бег быстрый темп",
    "сгибания рук с бутылками": "подъем гантелей на бицепс",
    "бросок мяча через голову назад": "медбол",
    "бросок мяча от груди вперед": "медбол",
    "бросок легкого мяча от груди вперед": "медбол",
    "бросок легкого мяча от груди технично": "медбол",
    "бросок медицинского мяча": "медбол",
    "бросок и ловля мяча с поворотом корпуса": "медбол",
    "бросок рюкзака мяча в пол": "медбол",
    "приставные шаги": "бег приставными шагами",
    "быстрые удары руками": "бой",
    "бой с тенью": "бой",
    "марш на месте": "бег сгибая ноги",
    "круговые движения руками": "разминка",
    "птица собака": "планка",
    "птица-собака с задержкой": "планка",
    "сгибание рук на нижнем блоке": "бицепс",
    "концентрированный подъем": "бицепс",
}

# Если точного матча нет — ищем по ключевому слову → запрос в каталог
_KEYWORD_FALLBACKS = (
    ("скакалк", "прыжки на скакалке"),
    ("берпи", "бурпи"),
    ("бурпи", "бурпи"),
    ("бёрпи", "бурпи"),
    ("отжим", "отжимания от пола"),
    ("присед", "приседания"),
    ("выпад", "выпады"),
    ("болгар", "болгарские приседания"),
    ("планк", "планка"),
    ("мост", "мостик"),
    ("ягодич", "мостик"),
    ("румын", "мертвая тяга"),
    ("мертв", "мертвая тяга"),
    ("станова", "становая тяга"),
    ("подтяг", "подтягивания"),
    ("тяга", "тяга гантели"),
    ("жим", "жим гантелей"),
    ("махи", "махи"),
    ("прыж", "прыжки"),
    ("запрыг", "прыжки на тумбу"),
    ("зашаг", "зашагивания"),
    ("тумб", "прыжки на тумбу"),
    ("коробк", "зашагивания на тумбу"),
    ("скручив", "пресс"),
    ("пресс", "пресс"),
    ("альпинист", "планка"),
    ("v-up", "пресс"),
    ("кардио", "бег средний"),
    ("дорожк", "бег средний"),
    ("спринт", "бег быстрый"),
    ("ходьб", "бег медленный"),
    ("бегов", "бег"),
    ("колен", "бег сгибая"),
    ("степ", "зашагивания"),
    ("шаг", "бег приставными"),
    ("размин", "разминка"),
    ("кругов", "разминка"),
    ("четверен", "планка"),
    ("бицепс", "бицепс"),
    ("сгибани", "бицепс"),
    ("концентр", "бицепс"),
    ("трицепс", "трицепс"),
    ("гантел", "гантел"),
    ("гир", "гир"),
    ("штан", "штан"),
    ("медбол", "медбол"),
    ("медицинск", "медбол"),
    ("бросок", "бросок"),
    ("плаван", "плавание"),
    ("вело", "вело"),
    ("разведен", "разведение гантелей"),
    ("суперсет", "гантел"),
)


def _clean_query(text: str) -> str:
    """Убирает OCR-мусор и повторы слов из названий PDF-планов."""
    n = _norm(text)
    if not n:
        return ""
    # частые артефакты OCR
    for junk in (
        " обычная планка руки",
        " обычные отжимания от пола",
        " обычные выпады назад",
        " обычная руки и ноги",
        " бросок голову назад",
        " бросок вперед руками",
        " бросок рукой вращение корпуса",
        " румынская гантелями двух",
        " румынская гантелями ногах",
        " ягодичный мост без бедрах веса",
        " ягодичный гантелью ногой",
        " тяга на скамье одной",
        " тяга резинки к себе одной рукой",
        " махи тяга к лицу суперсет стороны",
    ):
        # junk уже без ведущих пробелов (strip), заменяем целиком как фразу
        n = n.replace(junk.strip(), " ")
    parts = n.split()
    # убрать подряд идущие дубликаты слов
    cleaned: list[str] = []
    for w in parts:
        if not cleaned or cleaned[-1] != w:
            cleaned.append(w)
    return " ".join(cleaned).strip()


def _resolve_query(query: str) -> str:
    raw_q = _clean_query(query)
    if not raw_q:
        return ""
    if raw_q in _ALIASES:
        return _ALIASES[raw_q]
    # самый длинный алиас, который входит в запрос
    best_alias = ""
    best_target = raw_q
    for alias, target in _ALIASES.items():
        if alias in raw_q and len(alias) > len(best_alias):
            best_alias = alias
            best_target = target
    return best_target


def search(query: str, limit: int = 10, place: str | None = None) -> list[dict]:
    """Поиск по названию. place: home / gym / street / None."""
    items = load_catalog()
    raw_q = _clean_query(query)
    if not raw_q:
        return []

    q = _resolve_query(query)
    tokens = [t for t in q.split() if len(t) > 1]
    # значимые токены (не служебные)
    stop = {"с", "на", "в", "и", "или", "для", "без", "по", "к", "от", "из", "со", "при", "двух", "одной", "ноги", "руки"}
    significant = [t for t in tokens if t not in stop and len(t) > 2]

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
            score = 600 - min(len(title), 100)
        elif significant and all(t in title for t in significant):
            score = 350 + sum(30 for t in significant) - min(len(title), 50)
        else:
            hits = sum(1 for t in significant if t in title) if significant else 0
            if hits == 0:
                # хотя бы 1 сильный токен
                hits = sum(1 for t in tokens if len(t) > 3 and t in title)
                if hits == 0:
                    continue
                score = hits * 35 - min(len(title), 40)
            elif hits < max(1, (len(significant) + 1) // 2):
                continue
            else:
                score = hits * 55 - min(len(title), 40)

        # чуть выше приоритет у роликов с реальной ссылкой
        if item.get("video_url"):
            score += 5

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

    # keyword fallback: берём первое подходящее ключевое слово
    cleaned = _clean_query(exercise_name)
    for key, fallback_q in _KEYWORD_FALLBACKS:
        if key in cleaned:
            results = search(fallback_q, limit=5, place=None)
            if results:
                return results[0]
    return None


def bind_plan_exercises(plans: dict) -> int:
    """Проставляет video_url / video_title во всех упражнениях training_plans.
    Возвращает сколько упражнений получили ссылку (включая уже заполненные)."""
    bound = 0

    def walk(obj):
        nonlocal bound
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item.get("name"):
                    if item.get("video_url"):
                        bound += 1
                        continue
                    place = None
                    video = find_video(item["name"], place=place)
                    if video and video.get("video_url"):
                        item["video_url"] = video["video_url"]
                        item["video_title"] = video.get("title")
                        bound += 1
                else:
                    walk(item)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)

    walk(plans)
    return bound


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
