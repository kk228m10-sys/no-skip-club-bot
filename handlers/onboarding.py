from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import database as db
import keyboards as kb
from content import (
    LEVELS,
    GENDERS,
    TRAINING_PLACES,
    TRAINING_TYPES,
    PROMISES,
    DAY_SHORT,
    MIN_TRAINING_DAYS,
    MAX_TRAINING_TYPES,
    MIN_WEIGHT_KG,
    MAX_WEIGHT_KG,
    generate_weekly_plan,
)
import datetime
import json

router = Router()


class Onboarding(StatesGroup):
    waiting_gender = State()
    waiting_level = State()
    waiting_weight = State()
    waiting_training_days = State()
    waiting_place = State()
    waiting_training_types = State()
    waiting_promise = State()
    waiting_custom_promise = State()


WELCOME_TEXT = (
    "🖤 <b>Добро пожаловать в No Skip Club</b>\n"
    "Дисциплина или заплати.\n\n"
    "Это не очередной бот с мотивационными цитатами. Это твой трекер обязательств: "
    "план под твой уровень, честный учёт тренировок и стрик, который растёт "
    "только если ты реально занимаешься — или обнуляется, если пропускаешь.\n\n"
    "Отвечу на пару вопросов, чтобы собрать твой первый план. Это займёт минуту."
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = await db.ensure_user(message.from_user.id, message.from_user.username or "")

    if user["onboarded"]:
        await message.answer(
            f"С возвращением 👊 Ты уже в клубе.",
            reply_markup=kb.persistent_menu_kb(),
        )
        await message.answer("Главное меню:", reply_markup=kb.main_menu_kb())
        return

    await state.clear()
    await message.answer(WELCOME_TEXT)
    await message.answer("Для начала — укажи свой пол:", reply_markup=kb.gender_kb())
    await state.set_state(Onboarding.waiting_gender)


@router.callback_query(Onboarding.waiting_gender, F.data.startswith("onb_gender:"))
async def onb_gender(callback: CallbackQuery, state: FSMContext):
    gender = callback.data.split(":")[1]
    await state.update_data(gender=gender)
    await callback.message.edit_text(f"Пол: <b>{GENDERS[gender]}</b> ✅")
    await callback.message.answer("Какой у тебя уровень подготовки?", reply_markup=kb.levels_kb())
    await state.set_state(Onboarding.waiting_level)
    await callback.answer()


@router.callback_query(Onboarding.waiting_level, F.data.startswith("onb_level:"))
async def onb_level(callback: CallbackQuery, state: FSMContext):
    level = callback.data.split(":")[1]
    await state.update_data(level=level, training_days=[])
    await callback.message.edit_text(f"Уровень: <b>{LEVELS[level]}</b> ✅")
    await callback.message.answer(f"Какой у тебя вес сейчас? Напиши число в кг (например: 72).")
    await state.set_state(Onboarding.waiting_weight)
    await callback.answer()


@router.message(Onboarding.waiting_weight)
async def onb_weight(message: Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        weight = float(text)
    except ValueError:
        await message.answer(f"Не похоже на число. Напиши вес в кг цифрами, например: 72")
        return

    if not (MIN_WEIGHT_KG <= weight <= MAX_WEIGHT_KG):
        await message.answer(f"Введи реальный вес в кг — от {MIN_WEIGHT_KG} до {MAX_WEIGHT_KG}.")
        return

    await state.update_data(weight=weight)
    await message.answer(f"Вес: <b>{weight:g} кг</b> ✅")
    await message.answer(
        f"Сколько дней в неделю и в какие дни будешь тренироваться? "
        f"Выбери от {MIN_TRAINING_DAYS} до 7 дней, потом жми «Готово».",
        reply_markup=kb.training_days_kb(set()),
    )
    await state.set_state(Onboarding.waiting_training_days)


@router.callback_query(Onboarding.waiting_training_days, F.data.startswith("onb_day_toggle:"))
async def onb_day_toggle(callback: CallbackQuery, state: FSMContext):
    day_idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("training_days", []))

    if day_idx in selected:
        selected.discard(day_idx)
    else:
        selected.add(day_idx)

    await state.update_data(training_days=sorted(selected))
    await callback.message.edit_reply_markup(reply_markup=kb.training_days_kb(selected))
    await callback.answer()


@router.callback_query(Onboarding.waiting_training_days, F.data == "onb_days_done")
async def onb_days_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("training_days", [])

    if len(selected) < MIN_TRAINING_DAYS:
        await callback.answer(f"Выбери хотя бы {MIN_TRAINING_DAYS} дня", show_alert=True)
        return

    days_str = ", ".join(DAY_SHORT[i] for i in sorted(selected))
    await callback.message.edit_text(f"Тренировочные дни: <b>{days_str}</b> ✅")
    await callback.message.answer(
        "Где будешь тренироваться?",
        reply_markup=kb.training_place_kb(),
    )
    await state.set_state(Onboarding.waiting_place)
    await callback.answer()


@router.callback_query(Onboarding.waiting_place, F.data.startswith("onb_place:"))
async def onb_place(callback: CallbackQuery, state: FSMContext):
    place = callback.data.split(":")[1]
    await state.update_data(place=place, training_types=[])
    await callback.message.edit_text(f"Место тренировок: <b>{TRAINING_PLACES[place]}</b> ✅")
    await callback.message.answer(
        "Какой вид тренировок тебе нужен? Можно выбрать и совместить не более двух.",
        reply_markup=kb.training_types_kb(set()),
    )
    await state.set_state(Onboarding.waiting_training_types)
    await callback.answer()


@router.callback_query(Onboarding.waiting_training_types, F.data.startswith("onb_type_toggle:"))
async def onb_type_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    data = await state.get_data()
    selected = set(data.get("training_types", []))

    if key in selected:
        selected.discard(key)
    else:
        if len(selected) >= MAX_TRAINING_TYPES:
            await callback.answer(f"Можно выбрать не более {MAX_TRAINING_TYPES} видов", show_alert=True)
            return
        selected.add(key)

    await state.update_data(training_types=sorted(selected))
    await callback.message.edit_reply_markup(reply_markup=kb.training_types_kb(selected))
    await callback.answer()


@router.callback_query(Onboarding.waiting_training_types, F.data == "onb_type_done")
async def onb_types_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("training_types", [])

    if not selected:
        await callback.answer("Выбери хотя бы один вид тренировок", show_alert=True)
        return

    types_str = ", ".join(TRAINING_TYPES[k] for k in selected)
    await callback.message.edit_text(f"Вид тренировок: <b>{types_str}</b> ✅")
    await callback.message.answer(
        "Последнее — какое обещание ты даёшь себе на этот путь?",
        reply_markup=kb.promises_kb(),
    )
    await state.set_state(Onboarding.waiting_promise)
    await callback.answer()


@router.callback_query(Onboarding.waiting_promise, F.data.startswith("onb_promise:"))
async def onb_promise(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split(":")[1])
    if idx == len(PROMISES) - 1:
        await callback.message.edit_text("Напиши своё обещание одним сообщением:")
        await state.set_state(Onboarding.waiting_custom_promise)
        await callback.answer()
        return

    promise = PROMISES[idx]
    await finish_onboarding(callback.message, state, promise, callback.from_user.id)
    await callback.answer()


@router.message(Onboarding.waiting_custom_promise)
async def onb_custom_promise(message: Message, state: FSMContext):
    await finish_onboarding(message, state, message.text.strip(), message.from_user.id)


async def finish_onboarding(message: Message, state: FSMContext, promise: str, telegram_id: int):
    data = await state.get_data()
    level = data["level"]
    weight = data.get("weight")
    training_days = sorted(data["training_days"])
    place = data["place"]
    training_types = sorted(data["training_types"])

    await db.update_user(
        telegram_id,
        gender=data.get("gender"),
        level=level,
        weight=weight,
        training_days=json.dumps(training_days),
        days_per_week=len(training_days),
        training_place=place,
        training_types=json.dumps(training_types),
        goal=training_types[0] if training_types else None,
        promise=promise,
        onboarded=1,
        blocked=0,
    )

    plan = generate_weekly_plan(level, place, training_types, training_days=training_days)
    week_start = datetime.date.today().isoformat()
    await db.save_weekly_plan(telegram_id, week_start, plan)

    await state.clear()

    days_str = ", ".join(DAY_SHORT[i] for i in training_days)
    types_str = ", ".join(TRAINING_TYPES[k] for k in training_types)
    await message.answer(
        f"Обещание записано: «{promise}» ✍️\n\n"
        f"Твой первый план на неделю готов: {LEVELS[level]} уровень, {TRAINING_PLACES[place]}, "
        f"дни — {days_str}, вид тренировок — {types_str}.\n\n"
        f"Добро пожаловать в клуб. Дальше — только держать слово.",
        reply_markup=kb.persistent_menu_kb(),
    )
    await message.answer("Открыть меню:", reply_markup=kb.main_menu_kb())
