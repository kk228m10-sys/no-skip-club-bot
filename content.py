"""
Статический контент бота: тексты, библиотека упражнений, питание, генерация
недельного плана тренировок. Всё это легко редактировать и расширять —
просто дописывай в словари ниже, код менять не надо.
"""

import json
import random
from pathlib import Path

TRAINING_PLANS_PATH = Path(__file__).resolve().parent / "data" / "training_plans.json"
_training_plans_cache: dict | None = None


def _load_training_plans() -> dict:
    """Загружает реальные планы тренировок (разобранные из PDF под sportkuznica.com).

    Структура: {place: {category: {level: {"3"/"4"/"5": {день_название: [упражнения]}}}}}
    place: home / gym. category: fatloss/strength/endurance/explosive/ofp (=TRAINING_TYPES).
    Каждое упражнение: name, alt, sets_display, weight, rest, video_url?, video_title?

    Покрытие неполное: пара категорий/уровней и сплиты 6-7 дней ещё не разобраны
    из PDF (проблемы форматирования исходников) — для них используется
    старый резервный генератор на EXERCISE_LIBRARY ниже.
    """
    global _training_plans_cache
    if _training_plans_cache is not None:
        return _training_plans_cache
    if not TRAINING_PLANS_PATH.exists():
        _training_plans_cache = {}
        return _training_plans_cache
    with open(TRAINING_PLANS_PATH, encoding="utf-8") as f:
        _training_plans_cache = json.load(f)
    return _training_plans_cache

ABOUT_TEXT = (
    "🖤 <b>No Skip Club</b>\n"
    "Дисциплина или заплати.\n\n"
    "Мы — сообщество людей, которые устали от тренировок «когда будет настроение». "
    "No Skip Club построен на одной идее: результат даёт не мотивация, а система "
    "и обязательства, от которых нельзя тихо соскочить.\n\n"
    "Здесь нет магии и «одной техники, которая изменит всё». Есть план под твой "
    "уровень, трекинг честности с самим собой и сообщество, которому ты пообещал "
    "не пропускать.\n\n"
    "Пропустил — заплати. Себе, своему прогрессу, своему слову."
)

LEVELS = {
    "beginner": "Новичок",
    "intermediate": "Средний",
    "advanced": "Продвинутый",
}

# Пол пользователя — нужен для персонажа мини-аппа (мужская/женская модель).
GENDERS = {
    "male": "Мужской",
    "female": "Женский",
}


def get_character_archetype(goal: str) -> str:
    """Определяет архетип персонажа мини-аппа по цели тренировок.

    'loss' — цель «Похудение / рельеф»: персонаж стартует в лишнем весе
    и по мере роста стрика худеет, обретая форму.
    'gain' — цель «Сила / масса»: персонаж стартует худым и по мере
    роста стрика набирает мышцы.
    'maintain' — любая другая цель (выносливость, взрывная сила, ОФП,
    цель не задана и т.д.): персонаж стартует чуть слабее среднего
    и по мере роста стрика подтягивается к спортивной форме.
    """
    if goal == "fatloss":
        return "loss"
    if goal == "strength":
        return "gain"
    return "maintain"

TRAINING_PLACES = {
    "home": "Дома",
    "gym": "В зале",
}

# Виды (подтипы) тренировок. Можно выбрать и совмещать не более двух.
TRAINING_TYPES = {
    "fatloss": "Похудение / рельеф",
    "strength": "Сила / масса",
    "endurance": "Выносливость / координация",
    "explosive": "Взрывная сила",
    "ofp": "ОФП",
}

MAX_TRAINING_TYPES = 2
MIN_TRAINING_DAYS = 3
MAX_TRAINING_DAYS = 7
MIN_WEIGHT_KG = 30
MAX_WEIGHT_KG = 250

# Расписание записи на онлайн-встречу: день недели -> название,
# фиксированные часовые слоты, максимум участников на один слот.
BOOKING_DAYS = {2: "Среда", 5: "Суббота"}  # 0=Пн ... 6=Вс
BOOKING_SLOTS = ["17:00-18:00", "18:00-19:00", "19:00-20:00"]
MAX_BOOKING_PER_SLOT = 10

# Жесты для утренней фото-проверки тренировки. Каждый день бот выбирает один
# случайный жест, и в этот день пользователь должен прислать фото с этим
# жестом на фоне зала/дома, чтобы засчитать тренировку.
GESTURES = [
    {"key": "peace", "emoji": "✌️", "name": "Виктория (два пальца буквой V)"},
    {"key": "thumbsup", "emoji": "👍", "name": "Большой палец вверх"},
    {"key": "shaka", "emoji": "🤙", "name": "Шака — кулак с оттопыренными большим пальцем и мизинцем"},
    {"key": "fist", "emoji": "✊", "name": "Сжатый кулак"},
    {"key": "rock", "emoji": "🤟", "name": "Рок / «я тебя люблю» — указательный палец, мизинец и большой палец подняты"},
    {"key": "ok", "emoji": "👌", "name": "ОК — кольцо из большого и указательного пальцев"},
    {"key": "open", "emoji": "🖐", "name": "Открытая ладонь, пальцы врозь"},
]

VERIFICATION_SYSTEM_PROMPT = (
    "Ты — главный тренер фитнес-клуба No Skip Club. Твоя единственная задача — "
    "проверять фотографии, которые участники присылают как подтверждение тренировки. "
    "Тебе показывают фото и описание жеста руки, который человек должен на нём показывать.\n\n"
    "Проверь по фото:\n"
    "1. Действительно ли на фото виден человек, показывающий именно указанный жест рукой.\n"
    "2. Похоже ли фото на настоящий снимок из спортзала или из дома (видна тренировочная "
    "обстановка — зал, тренажёры, коврик, гантели, домашнее пространство и т.п.), а не на "
    "сгенерированное нейросетью изображение, скриншот, рисунок, фото экрана или чужое фото "
    "из интернета.\n\n"
    "Если оба условия выполняются — ответь ровно одним словом: ПОЛОЖИТЕЛЬНО\n"
    "Если хотя бы одно условие не выполняется, или ты не уверен — ответь ровно одним словом: "
    "ОТРИЦАТЕЛЬНО\n\n"
    "Не пиши ничего, кроме этого одного слова. Никаких объяснений, разговоров, извинений "
    "или комментариев — только вердикт."
)


AI_SYSTEM_PROMPT = (
    "Ты — тёплый и опытный спортивный психолог, который умеет находить общий язык с людьми "
    "любого возраста. К тебе обращаются участники фитнес-клуба «No Skip Club», где действует "
    "правило: пропустил тренировочный день — платишь штраф. Это часть правил клуба и способ "
    "держать дисциплину, а не наказание из вредности.\n\n"
    "Твоя задача:\n"
    "1. Внимательно и без осуждения выслушать проблему человека — усталость, лень, страх, "
    "нехватку времени, боль, выгорание, что угодно.\n"
    "2. Отнестись с эмпатией, поддержать по-человечески, не сухим казённым языком.\n"
    "3. Помочь найти самый мягкий и реалистичный компромисс: изменить время тренировки, "
    "снизить интенсивность, адаптировать план под текущее состояние, разбить тренировку на части — "
    "но не предлагать просто бросить или пропустить без последствий.\n"
    "4. В конце разговора мягко, но уверенно подвести человека к мысли, что тренировки нужно "
    "продолжать, а правило платить за пропуски — это нормально и справедливо: оно помогает не "
    "бросить дело на полпути и уважать собственное слово.\n\n"
    "Не используй резкие фразы вроде «соберись» или «не ной». Веди себя как заботливый наставник, "
    "которому не всё равно. Отвечай на русском языке, если человек не написал тебе на другом."
)

PROMISES = [
    "Не пропускать тренировочные дни ни при каких оправданиях",
    "Делать хотя бы минимум, даже если нет сил на полную",
    "Не врать себе в трекере — если пропустил, так и отметить",
    "Своя формулировка",
]

# ---------------------------------------------------------------------------
# Библиотека упражнений: place -> level -> список упражнений с техникой.
# У каждого упражнения есть "types" — какие виды тренировок оно закрывает.
# ---------------------------------------------------------------------------

EXERCISE_LIBRARY = {
    "home": {
        "beginner": [
            {
                "name": "Приседания с собственным весом",
                "sets": "3x12-15",
                "types": ["strength", "ofp", "fatloss"],
                "technique": (
                    "Стопы на ширине плеч, спина прямая, взгляд вперёд. Опускайся, "
                    "будто садишься на стул, колени не выходят сильно за носки. "
                    "Внизу бёдра параллельны полу или чуть выше."
                ),
            },
            {
                "name": "Отжимания с колен или от стены",
                "sets": "3x8-12",
                "types": ["strength", "ofp"],
                "technique": (
                    "Корпус — прямая линия от головы до колен, локти под 45° к телу, "
                    "опускайся до угла в локте ~90°, не роняй таз."
                ),
            },
            {
                "name": "Планка",
                "sets": "3x20-30 сек",
                "types": ["ofp", "endurance"],
                "technique": (
                    "Локти под плечами, тело прямое от макушки до пяток, живот "
                    "напряжён, таз не проваливается и не задирается вверх."
                ),
            },
            {
                "name": "Выпады на месте",
                "sets": "3x10 на ногу",
                "types": ["strength", "fatloss", "ofp"],
                "technique": (
                    "Шаг вперёд, оба колена сгибаются до ~90°, заднее колено не "
                    "касается пола, корпус вертикально."
                ),
            },
            {
                "name": "Ягодичный мостик",
                "sets": "3x15",
                "types": ["strength", "ofp"],
                "technique": (
                    "Лёжа на спине, стопы под коленями, поднимай таз, сжимая "
                    "ягодицы вверху, без прогиба в пояснице."
                ),
            },
        ],
        "intermediate": [
            {
                "name": "Приседания с паузой",
                "sets": "4x12",
                "types": ["strength", "ofp"],
                "technique": "Как обычный присед, но задержка 2 сек в нижней точке — держит форму под контролем.",
            },
            {
                "name": "Отжимания классические",
                "sets": "4x12-15",
                "types": ["strength", "ofp"],
                "technique": "Прямая линия тела, локти прижаты ближе к корпусу, полная амплитуда вниз-вверх.",
            },
            {
                "name": "Берпи",
                "sets": "4x10",
                "types": ["fatloss", "endurance", "explosive"],
                "technique": "Присед — упор лёжа — отжимание — прыжок ногами к рукам — выпрыгивание вверх, без потери техники в темпе.",
            },
            {
                "name": "Болгарские выпады (нога на возвышении)",
                "sets": "3x10 на ногу",
                "types": ["strength"],
                "technique": "Задняя стопа на скамье/стуле, опускайся вертикально, вес на передней ноге.",
            },
            {
                "name": "Планка с касанием плеча",
                "sets": "3x30-40 сек",
                "types": ["ofp", "endurance"],
                "technique": "В планке на руках поочерёдно касайся ладонью противоположного плеча, таз не раскачивается.",
            },
        ],
        "advanced": [
            {
                "name": "Пистолетик (присед на одной ноге)",
                "sets": "4x6-8 на ногу",
                "types": ["strength", "explosive"],
                "technique": "Вторая нога вытянута вперёд, опускайся медленно и подконтрольно, спина прямая.",
            },
            {
                "name": "Отжимания с хлопком / на возвышении",
                "sets": "4x10-12",
                "types": ["explosive", "strength"],
                "technique": "Взрывное отжимание вверх, мягкое приземление, контроль на опускании.",
            },
            {
                "name": "Берпи с прыжком на возвышение",
                "sets": "5x10",
                "types": ["explosive", "endurance", "fatloss"],
                "technique": "Полный цикл берпи, финальный прыжок на устойчивую платформу.",
            },
            {
                "name": "Выпрыгивания из глубокого приседа",
                "sets": "4x12",
                "types": ["explosive", "fatloss"],
                "technique": "Полная амплитуда вниз, мощный взрыв вверх, мягкое приземление в присед.",
            },
            {
                "name": "Планка с подтягиванием колена к локтю",
                "sets": "4x40 сек",
                "types": ["ofp", "endurance"],
                "technique": "Из планки поочерёдно подтягивай колено к локтю той же стороны, темп средний, техника важнее скорости.",
            },
        ],
    },
    "gym": {
        "beginner": [
            {
                "name": "Жим ногами в тренажёре",
                "sets": "3x12",
                "types": ["strength", "ofp"],
                "technique": "Стопы на ширине плеч на платформе, опускай платформу до угла в колене ~90°, не отрывай поясницу от спинки.",
            },
            {
                "name": "Тяга верхнего блока к груди",
                "sets": "3x12",
                "types": ["strength"],
                "technique": "Хват чуть шире плеч, тяни к верху груди, лопатки своди, корпус не раскачивай.",
            },
            {
                "name": "Жим гантелей лёжа на скамье",
                "sets": "3x10-12",
                "types": ["strength"],
                "technique": "Гантели над грудью на вытянутых руках, опускай подконтрольно до уровня груди, локти не разводи в стороны резко.",
            },
            {
                "name": "Кардио на дорожке или велотренажёре",
                "sets": "1x15-20 мин",
                "types": ["endurance", "fatloss"],
                "technique": "Держи равномерный темп, при котором можешь говорить короткими фразами, но не петь песню.",
            },
            {
                "name": "Скручивания на пресс-тренажёре",
                "sets": "3x15",
                "types": ["ofp"],
                "technique": "Скручивай корпус за счёт пресса, а не рывком рук, в верхней точке — короткая пауза.",
            },
        ],
        "intermediate": [
            {
                "name": "Приседания со штангой",
                "sets": "4x10",
                "types": ["strength", "ofp", "explosive"],
                "technique": "Штанга на трапециях, спина прямая, приседай до параллели бёдер с полом, колени по направлению носков.",
            },
            {
                "name": "Становая тяга на прямых ногах",
                "sets": "4x8",
                "types": ["strength"],
                "technique": "Гриф скользит вдоль ног, спина прямая, наклон за счёт таза, лёгкий сгиб в коленях.",
            },
            {
                "name": "Жим штанги лёжа",
                "sets": "4x8-10",
                "types": ["strength"],
                "technique": "Лопатки сведены, гриф опускается к нижней части груди, локти под углом ~45° к корпусу.",
            },
            {
                "name": "Интервальный бег или гребной тренажёр",
                "sets": "6 раундов: 1 мин быстро / 1 мин медленно",
                "types": ["endurance", "fatloss", "explosive"],
                "technique": "На быстрых отрезках выкладывайся на 80-90%, на медленных — восстанавливай дыхание, не останавливайся полностью.",
            },
            {
                "name": "Планка с диском на спине",
                "sets": "3x40 сек",
                "types": ["ofp"],
                "technique": "Классическая планка, диск кладёшь на поясницу для доп. нагрузки, таз не проваливается.",
            },
        ],
        "advanced": [
            {
                "name": "Толчковый жим штанги стоя (push press)",
                "sets": "5x5",
                "types": ["explosive", "strength"],
                "technique": "Лёгкий полуприсед для импульса, затем взрывной жим штанги над головой, фиксация вверху.",
            },
            {
                "name": "Приседания со штангой тяжёлые",
                "sets": "5x5",
                "types": ["strength"],
                "technique": "Рабочий вес 80%+ от разового максимума, обязательна разминка и контроль техники на каждой фазе.",
            },
            {
                "name": "Спринты на беговой дорожке",
                "sets": "8x20 сек в полную силу",
                "types": ["explosive", "endurance", "fatloss"],
                "technique": "Максимальное ускорение 20 секунд, затем 40 секунд шагом для восстановления, следи за пульсом.",
            },
            {
                "name": "Кроссфит-комплекс (берпи + гребля + приседания)",
                "sets": "4 раунда без остановки",
                "types": ["fatloss", "endurance", "explosive"],
                "technique": "10 берпи, 250м гребли, 15 приседаний с весом — темп высокий, но техника не должна разваливаться.",
            },
            {
                "name": "Турецкий подъём с гирей",
                "sets": "3x5 на каждую сторону",
                "types": ["ofp", "strength"],
                "technique": "Медленный контролируемый подъём из положения лёжа в стойку с гирей над головой, взгляд на гирю.",
            },
        ],
    },
}

REST_DAY_TIP = (
    "Сегодня день отдыха — это тоже часть плана, а не пропуск. "
    "Лёгкая растяжка, прогулка 20-30 минут и вода — этого достаточно."
)

NUTRITION_TIPS = {
    "fatloss": [
        "Белок в каждый приём пищи — он держит сытость дольше всего.",
        "Не убирай жиры полностью — они нужны для гормонального фона, просто не превышай норму.",
        "Пей воду перед едой — часто голод путают с жаждой.",
        "Считай не только калории, но и то, насколько еда тебя насыщает — овощи и белок эффективнее пустых калорий.",
    ],
    "strength": [
        "Ешь достаточно белка — ориентир 1.6-2.2 г на кг веса тела в день.",
        "Не тренируйся совсем голодным — за 1.5-2 часа до тренировки нужен приём пищи с углеводами.",
        "После тренировки — белок и углеводы в течение 1-2 часов для восстановления.",
        "Сон не менее 7 часов — мышцы растут не в зале, а во время отдыха.",
    ],
    "endurance": [
        "Углеводы — твоё топливо, не бойся их перед длительной нагрузкой.",
        "Следи за электролитами при долгих тренировках — не только вода, но и соли.",
        "Ешь за 2-3 часа до длительной тренировки, лёгкий перекус — за 30-60 минут.",
        "Восстановление через питание так же важно, как сама тренировка.",
    ],
    "explosive": [
        "Углеводы перед тренировкой дают энергию для взрывных движений — не тренируйся голодным.",
        "Давай себе полноценный отдых между подходами (2-3 минуты) — нервной системе нужно восстановиться.",
        "Добавки вроде креатина иногда помогают с силовой выносливостью, но перед приёмом посоветуйся с врачом.",
        "Сон и восстановление критичны — взрывные тренировки сильно нагружают нервную систему.",
    ],
    "ofp": [
        "Разнообразь рацион — ОФП нагружает всё тело, и организму нужны разные нутриенты.",
        "Не пренебрегай белком даже без цели «накачаться» — он нужен для восстановления связок и суставов.",
        "Пей достаточно воды в течение дня, а не только во время тренировки.",
        "Ешь овощи и клетчатку — при общей физической подготовке важны и энергия на день, и работа кишечника.",
    ],
}

# Коэффициенты для приблизительного расчёта КБЖУ по весу и выбранной
# программе (виду тренировок). ккал/кг — суточная калорийность на кг веса,
# белок/жир — граммы на кг веса. Углеводы досчитываются по остатку калорий.
GOAL_KBJU_COEFFICIENTS = {
    "fatloss": {"kcal_per_kg": 27, "protein_per_kg": 2.0, "fat_per_kg": 0.9},
    "strength": {"kcal_per_kg": 34, "protein_per_kg": 2.0, "fat_per_kg": 1.0},
    "endurance": {"kcal_per_kg": 32, "protein_per_kg": 1.6, "fat_per_kg": 1.0},
    "explosive": {"kcal_per_kg": 33, "protein_per_kg": 1.8, "fat_per_kg": 1.0},
    "ofp": {"kcal_per_kg": 30, "protein_per_kg": 1.6, "fat_per_kg": 1.0},
}


def calculate_kbju(weight: float, goal: str) -> dict:
    """Приблизительный расчёт суточной нормы КБЖУ по весу (кг) и программе.

    Это упрощённая оценка (без роста/возраста/пола), основанная только на
    весе и типе тренировок — этого достаточно для ориентировочных цифр.
    """
    coef = GOAL_KBJU_COEFFICIENTS.get(goal, GOAL_KBJU_COEFFICIENTS["ofp"])
    calories = round(weight * coef["kcal_per_kg"])
    protein = round(weight * coef["protein_per_kg"])
    fat = round(weight * coef["fat_per_kg"])
    carbs = max(0, round((calories - protein * 4 - fat * 9) / 4))
    return {"calories": calories, "protein": protein, "fat": fat, "carbs": carbs}


DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

# Как распределять тренировочные дни по неделе в зависимости от days_per_week
# (используется только как запасной вариант для старых аккаунтов без явного
# списка дней).
DISTRIBUTION = {
    1: [0],
    2: [0, 3],
    3: [0, 2, 4],
    4: [0, 1, 3, 4],
    5: [0, 1, 2, 3, 4],
    6: [0, 1, 2, 3, 4, 5],
    7: [0, 1, 2, 3, 4, 5, 6],
}


def _generate_weekly_plan_legacy(level: str, place: str = "home", training_types=None, training_days=None, days_per_week: int = None):
    """Старый резервный генератор: случайные 4 упражнения из EXERCISE_LIBRARY.
    Используется только когда для нужного места/цели/уровня ещё нет реального
    PDF-плана (сплиты 6-7 дней, пара категорий с проблемным исходником)."""
    if training_days is None:
        days_per_week = max(1, min(7, days_per_week or 3))
        training_days = DISTRIBUTION.get(days_per_week, DISTRIBUTION[3])

    training_indices = set(training_days)
    place = place if place in EXERCISE_LIBRARY else "home"
    pool = EXERCISE_LIBRARY.get(place, {}).get(level, EXERCISE_LIBRARY[place]["beginner"])

    types_set = set(training_types or [])
    if types_set:
        filtered = [ex for ex in pool if types_set & set(ex.get("types", []))]
        if filtered:
            pool = filtered

    plan = {}
    for i, day_name in enumerate(DAYS_RU):
        if i in training_indices:
            exercises = random.sample(pool, k=min(4, len(pool)))
            plan[day_name] = {"rest": False, "exercises": exercises}
        else:
            plan[day_name] = {"rest": True, "exercises": []}
    return plan


def _real_plan_days(place: str, category: str, level: str, split: str) -> list | None:
    """Список [(день_название, [упражнения])] для place/category/level/split,
    или None если такого разбора PDF ещё нет."""
    plans = _load_training_plans()
    days = plans.get(place, {}).get(category, {}).get(level, {}).get(split)
    if not days:
        return None
    return [(label, exs) for label, exs in days.items() if exs]


def _pick_split(place: str, category: str, level: str, days_per_week: int):
    """Подбирает лучший доступный сплит (3/4/5 дней) под желаемое кол-во
    тренировочных дней в неделю. Возвращает (список дней плана, split_used)."""
    available = {}
    for split in ("3", "4", "5"):
        d = _real_plan_days(place, category, level, split)
        if d:
            available[int(split)] = d
    if not available:
        return None
    # ближайший доступный сплит к желаемому кол-ву дней
    best = min(available.keys(), key=lambda s: abs(s - days_per_week))
    return available[best], best


def _compose_6_7_day_plan(place: str, category: str, level: str, n_days: int):
    """6 и 7 тренировочных дней в неделю сами PDF не расписывают отдельной
    таблицей — там прямым текстом сказано: "Дни 1,3,5 — основные тренировки
    (как в 3-дневной программе), дни 2,4(,6,7) — лёгкие дни (как в 5-дневной
    программе)". Собираем план именно по этому правилу: чередуем основной
    (3-дневный) и лёгкий (5-дневный) пул упражнений по позициям.
    Возвращает список [(label, exs), ...] длиной n_days, либо None."""
    main_pool = _real_plan_days(place, category, level, "3")
    light_pool = (
        _real_plan_days(place, category, level, "5")
        or _real_plan_days(place, category, level, "4")
        or main_pool
    )
    if not main_pool or not light_pool:
        return None

    result = []
    mi = li = 0
    for pos in range(n_days):  # pos 0,2,4.. (1,3,5 по-человечески) -> основной день
        if pos % 2 == 0:
            label, exs = main_pool[mi % len(main_pool)]
            mi += 1
        else:
            label, exs = light_pool[li % len(light_pool)]
            li += 1
        result.append((f"{label} (лёгкий день)" if pos % 2 else label, exs))
    return result


def _plan_days_for(place: str, category: str, level: str, n_days: int):
    """Единая точка входа: подбирает список тренировочных дней под нужное
    кол-во тренировок в неделю — с полноценной композицией для 6-7 дней."""
    if n_days >= 6:
        composed = _compose_6_7_day_plan(place, category, level, n_days)
        if composed:
            return composed
    picked = _pick_split(place, category, level, n_days)
    return picked[0] if picked else None


def _exercise_to_display(ex: dict) -> dict:
    """Приводит упражнение из training_plans.json к формату, который ждёт
    handlers/training.py: name, sets, technique, video_url?, video_title?."""
    bits = []
    if ex.get("weight"):
        bits.append(f"Вес: {ex['weight']}")
    if ex.get("rest"):
        bits.append(f"Отдых: {ex['rest']}")
    if ex.get("alt"):
        bits.append(f"Замена: {ex['alt']}")
    technique = ". ".join(bits) + ("." if bits else "")
    if not technique:
        technique = "Следи за техникой — при сомнениях смотри видео."
    out = {
        "name": ex["name"],
        "sets": ex.get("sets_display") or "-",
        "technique": technique,
    }
    if ex.get("video_url"):
        out["video_url"] = ex["video_url"]
        out["video_title"] = ex.get("video_title")
    return out


def generate_weekly_plan(level: str, place: str = "home", training_types=None, training_days=None, days_per_week: int = None):
    """Возвращает dict: {день_недели: {exercises: [...]} или {rest: True}}

    Сначала пытается собрать план из реальных программ тренировок
    (data/training_plans.json, разобрано из PDF под sportkuznica.com — со
    сплитами на 3/4/5 дней, привязанными видео техники). Если для нужной
    связки место/цель/уровень таких данных ещё нет — используется старый
    резервный генератор на EXERCISE_LIBRARY.

    place — "home" (дом+улица) или "gym". training_types — 1-2 ключа
    TRAINING_TYPES; если два — тренировочные дни чередуются между целями.
    training_days — явный список индексов дней недели (0=Пн...6=Вс).
    """
    if training_days is None:
        days_per_week = max(1, min(7, days_per_week or 3))
        training_days = DISTRIBUTION.get(days_per_week, DISTRIBUTION[3])

    training_indices = sorted(set(training_days))
    place_key = place if place in ("home", "gym") else "home"
    types = [t for t in (training_types or []) if t in TRAINING_TYPES] or ["ofp"]

    # для каждой выбранной цели пытаемся получить реальный сплит
    per_type_days = {}
    for cat in types:
        day_list = _plan_days_for(place_key, cat, level, len(training_indices))
        if day_list:
            per_type_days[cat] = day_list  # список [(label, exs), ...]

    if not per_type_days:
        # ни для одной выбранной цели нет разобранного плана -> резервный генератор
        return _generate_weekly_plan_legacy(level, place, training_types, training_days, days_per_week)

    # чередуем цели по дням недели, если их несколько
    ordered_types = [t for t in types if t in per_type_days] or list(per_type_days)
    plan = {}
    counters = {t: 0 for t in ordered_types}
    for pos, i in enumerate(training_indices):
        day_name = DAYS_RU[i]
        cat = ordered_types[pos % len(ordered_types)]
        day_list = per_type_days[cat]
        label, exs = day_list[counters[cat] % len(day_list)]
        counters[cat] += 1
        plan[day_name] = {
            "rest": False,
            "exercises": [_exercise_to_display(e) for e in exs],
            "focus": label,
        }
    for i, day_name in enumerate(DAYS_RU):
        if i not in training_indices:
            plan[day_name] = {"rest": True, "exercises": []}
    return plan


DAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def weekday_index_today():
    import datetime
    return datetime.date.today().weekday()  # 0 = понедельник
