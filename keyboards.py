from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from content import (
    LEVELS,
    GENDERS,
    TRAINING_PLACES,
    TRAINING_TYPES,
    PROMISES,
    DAY_SHORT,
    MIN_TRAINING_DAYS,
    MAX_TRAINING_TYPES,
    MAX_BOOKING_PER_SLOT,
)
import config


def gender_kb(prefix: str = "onb_gender"):
    rows = [[InlineKeyboardButton(text=v, callback_data=f"{prefix}:{k}")] for k, v in GENDERS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def levels_kb(prefix: str = "onb_level"):
    rows = [[InlineKeyboardButton(text=v, callback_data=f"{prefix}:{k}")] for k, v in LEVELS.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def training_days_kb(selected: set, prefix: str = "onb_day"):
    rows = []
    row = []
    for i, label in enumerate(DAY_SHORT):
        text = f"✅ {label}" if i in selected else label
        row.append(InlineKeyboardButton(text=text, callback_data=f"{prefix}_toggle:{i}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if len(selected) < MIN_TRAINING_DAYS:
        done_text = f"Выбери хотя бы {MIN_TRAINING_DAYS} дня"
    else:
        done_text = f"Готово ({len(selected)} дн.) ▶️"
    rows.append([InlineKeyboardButton(text=done_text, callback_data=f"{prefix}s_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def training_place_kb(prefix: str = "onb_place"):
    rows = [[InlineKeyboardButton(text=v, callback_data=f"{prefix}:{k}")] for k, v in TRAINING_PLACES.items()]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def training_types_kb(selected: set, prefix: str = "onb_type"):
    rows = []
    for k, v in TRAINING_TYPES.items():
        text = f"✅ {v}" if k in selected else v
        rows.append([InlineKeyboardButton(text=text, callback_data=f"{prefix}_toggle:{k}")])

    if not selected:
        done_text = "Выбери хотя бы один вид"
    else:
        done_text = f"Готово ({len(selected)}/{MAX_TRAINING_TYPES}) ▶️"
    rows.append([InlineKeyboardButton(text=done_text, callback_data=f"{prefix}_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def promises_kb():
    rows = []
    for i, p in enumerate(PROMISES):
        rows.append([InlineKeyboardButton(text=p, callback_data=f"onb_promise:{i}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_kb():
    buttons = [
        [InlineKeyboardButton(text="📊 Мой прогресс", callback_data="menu_progress")],
        [InlineKeyboardButton(text="🏋️ План на неделю", callback_data="menu_plan")],
        [InlineKeyboardButton(text="⚙️ Изменить план (уровень/дни/место/вид)", callback_data="menu_settings")],
        [InlineKeyboardButton(text="📋 Упражнения и техника", callback_data="menu_exercises")],
        [InlineKeyboardButton(text="🎬 Видео упражнений", callback_data="menu_videos")],
        [InlineKeyboardButton(text="🎥 Материалы (фото/видео)", callback_data="menu_media")],
        [InlineKeyboardButton(text="📸 Подтвердить тренировку", callback_data="menu_confirm_photo")],
        [InlineKeyboardButton(text="🥗 Питание", callback_data="menu_nutrition")],
        [InlineKeyboardButton(text="📅 Записаться на созвон", callback_data="menu_booking")],
        [InlineKeyboardButton(text="🧠 ИИ-психолог", callback_data="menu_ai_psych")],
        [InlineKeyboardButton(text="ℹ️ О проекте", callback_data="menu_about")],
    ]
    # Персонаж скрыт, пока CHARACTER_ENABLED=false (код и webapp остаются)
    if config.CHARACTER_ENABLED and config.WEBAPP_URL:
        buttons.insert(
            0,
            [InlineKeyboardButton(text="🎮 Мой персонаж", web_app=WebAppInfo(url=config.WEBAPP_URL))],
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def persistent_menu_kb():
    """Обычная (не inline) клавиатура с одной кнопкой — всегда видна под полем
    ввода, чтобы меню было легко найти в любой момент."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="☰ Меню")]],
        resize_keyboard=True,
        is_persistent=True,
    )


def back_to_menu_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")]]
    )


def workout_done_kb(include_videos: bool = True):
    rows = []
    if include_videos:
        rows.append(
            [InlineKeyboardButton(text="🎬 Видео техники на сегодня", callback_data="plan_today_videos")]
        )
    rows.append(
        [InlineKeyboardButton(text="📸 Подтвердить тренировку (фото)", callback_data="menu_confirm_photo")]
    )
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_rest_kb(include_videos: bool = False):
    rows = []
    if include_videos:
        rows.append(
            [InlineKeyboardButton(text="🎬 Видео техники на сегодня", callback_data="plan_today_videos")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_proof_kb(proof_id: int):
    """Кнопки для админа: засчитать / отклонить заявку на тренировку."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Засчитать", callback_data=f"admin_approve:{proof_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{proof_id}"),
            ]
        ]
    )


def feeling_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="😄 Легко", callback_data="feel:easy"),
                InlineKeyboardButton(text="😐 Нормально", callback_data="feel:normal"),
                InlineKeyboardButton(text="😞 Тяжело", callback_data="feel:hard"),
            ]
        ]
    )


def nutrition_goals_kb():
    rows = [[InlineKeyboardButton(text=v, callback_data=f"nutr:{k}")] for k, v in TRAINING_TYPES.items()]
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def end_ai_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Завершить разговор", callback_data="ai_end")]]
    )


def booking_slots_kb(slots_data):
    """slots_data — список dict-ов {date, label, slot, count, full} из handlers/booking.py"""
    rows = []
    for i, s in enumerate(slots_data):
        text = f"{s['label']} {s['date'].strftime('%d.%m')} {s['slot']} ({s['count']}/{MAX_BOOKING_PER_SLOT})"
        if s["full"]:
            text += " 🚫"
        rows.append([InlineKeyboardButton(text=text, callback_data=f"book:{s['date'].isoformat()}:{s['slot_idx']}")])
    rows.append([InlineKeyboardButton(text="📋 Мои записи", callback_data="my_bookings")])
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_bookings_kb(bookings):
    """bookings — список dict-ов {id, label, date_str, slot} из handlers/booking.py"""
    rows = []
    for b in bookings:
        rows.append(
            [InlineKeyboardButton(
                text=f"❌ Отменить: {b['label']} {b['date_str']} {b['slot']}",
                callback_data=f"cancelbook:{b['id']}",
            )]
        )
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_menu_kb():
    rows = []
    # Пол нужен в основном для персонажа — скрываем, пока персонаж выключен
    if config.CHARACTER_ENABLED:
        rows.append([InlineKeyboardButton(text="🚻 Пол (для персонажа)", callback_data="set_gender")])
    rows.extend([
        [InlineKeyboardButton(text="🎚 Уровень подготовки", callback_data="set_level")],
        [InlineKeyboardButton(text="📅 Дни и количество тренировок", callback_data="set_days")],
        [InlineKeyboardButton(text="🏠 Место (дома / в зале)", callback_data="set_place")],
        [InlineKeyboardButton(text="🏋️ Вид тренировок", callback_data="menu_change_types")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
