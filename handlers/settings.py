import datetime
import json

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
from content import LEVELS, GENDERS, TRAINING_PLACES, DAY_SHORT, MIN_TRAINING_DAYS, generate_weekly_plan

router = Router()


class ChangeGender(StatesGroup):
    waiting_gender = State()


class ChangeLevel(StatesGroup):
    waiting_level = State()


class ChangeDays(StatesGroup):
    waiting_days = State()


class ChangePlace(StatesGroup):
    waiting_place = State()


async def regenerate_and_reply(callback: CallbackQuery, header_text: str):
    """Пересобирает план на текущую неделю под актуальные уровень/место/дни/виды
    пользователя и показывает подтверждение."""
    user = await db.get_user(callback.from_user.id)
    place = user.get("training_place") or "home"
    try:
        types = json.loads(user.get("training_types") or "[]")
    except (TypeError, ValueError):
        types = []
    if not types:
        types = ["ofp"]

    training_days_raw = user.get("training_days")
    training_days = json.loads(training_days_raw) if training_days_raw else None

    plan = generate_weekly_plan(
        user["level"], place, types, training_days=training_days, days_per_week=user.get("days_per_week")
    )
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    await db.save_weekly_plan(callback.from_user.id, week_start.isoformat(), plan)

    await callback.message.edit_text(
        f"{header_text}\nПлан на неделю пересобран под новые параметры.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu_settings")
async def menu_settings(callback: CallbackQuery):
    await callback.message.edit_text(
        "⚙️ Что хочешь изменить?",
        reply_markup=kb.settings_menu_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Смена пола (влияет только на внешний вид персонажа в мини-аппе)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "set_gender")
async def set_gender_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Укажи свой пол — от этого зависит, как выглядит твой персонаж:",
        reply_markup=kb.gender_kb(prefix="chgender"),
    )
    await state.set_state(ChangeGender.waiting_gender)
    await callback.answer()


@router.callback_query(ChangeGender.waiting_gender, F.data.startswith("chgender:"))
async def set_gender_done(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, gender=gender)
    await state.clear()
    await callback.message.edit_text(
        f"Пол обновлён: <b>{GENDERS[gender]}</b> ✅\nПерсонаж в мини-аппе обновится автоматически.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Смена уровня подготовки
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "set_level")
async def set_level_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Выбери новый уровень подготовки:",
        reply_markup=kb.levels_kb(prefix="chlvl"),
    )
    await state.set_state(ChangeLevel.waiting_level)
    await callback.answer()


@router.callback_query(ChangeLevel.waiting_level, F.data.startswith("chlvl:"))
async def set_level_done(callback: CallbackQuery, state: FSMContext):
    level = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, level=level)
    await state.clear()
    await regenerate_and_reply(callback, f"Уровень обновлён: <b>{LEVELS[level]}</b> ✅")


# ---------------------------------------------------------------------------
# Смена количества и конкретных дней тренировок (от 3 до 7)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "set_days")
async def set_days_start(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    try:
        current = set(json.loads(user.get("training_days") or "[]"))
    except (TypeError, ValueError):
        current = set()

    await state.update_data(days=sorted(current))
    await callback.message.edit_text(
        f"Выбери от {MIN_TRAINING_DAYS} до 7 тренировочных дней:",
        reply_markup=kb.training_days_kb(current, prefix="chday"),
    )
    await state.set_state(ChangeDays.waiting_days)
    await callback.answer()


@router.callback_query(ChangeDays.waiting_days, F.data.startswith("chday_toggle:"))
async def set_days_toggle(callback: CallbackQuery, state: FSMContext):
    day_idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("days", []))

    if day_idx in selected:
        selected.discard(day_idx)
    else:
        selected.add(day_idx)

    await state.update_data(days=sorted(selected))
    await callback.message.edit_reply_markup(reply_markup=kb.training_days_kb(selected, prefix="chday"))
    await callback.answer()


@router.callback_query(ChangeDays.waiting_days, F.data == "chdays_done")
async def set_days_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("days", [])

    if len(selected) < MIN_TRAINING_DAYS:
        await callback.answer(f"Выбери хотя бы {MIN_TRAINING_DAYS} дня", show_alert=True)
        return

    selected = sorted(selected)
    await db.update_user(
        callback.from_user.id,
        training_days=json.dumps(selected),
        days_per_week=len(selected),
    )
    await state.clear()

    days_str = ", ".join(DAY_SHORT[i] for i in selected)
    await regenerate_and_reply(callback, f"Дни тренировок обновлены: <b>{days_str}</b> ✅")


# ---------------------------------------------------------------------------
# Смена места тренировок (дома / в зале)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "set_place")
async def set_place_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Где будешь тренироваться?",
        reply_markup=kb.training_place_kb(prefix="chplace"),
    )
    await state.set_state(ChangePlace.waiting_place)
    await callback.answer()


@router.callback_query(ChangePlace.waiting_place, F.data.startswith("chplace:"))
async def set_place_done(callback: CallbackQuery, state: FSMContext):
    place = callback.data.split(":")[1]
    await db.update_user(callback.from_user.id, training_place=place)
    await state.clear()
    await regenerate_and_reply(callback, f"Место тренировок обновлено: <b>{TRAINING_PLACES[place]}</b> ✅")
