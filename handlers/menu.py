from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

import json

import config
import database as db
import keyboards as kb
from content import ABOUT_TEXT, LEVELS, TRAINING_PLACES, TRAINING_TYPES

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=kb.main_menu_kb())


@router.message(F.text == "☰ Меню")
async def reply_menu_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=kb.main_menu_kb())


@router.callback_query(F.data == "menu_back")
async def menu_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=kb.main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_about")
async def menu_about(callback: CallbackQuery):
    await callback.message.edit_text(ABOUT_TEXT, reply_markup=kb.back_to_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "menu_progress")
async def menu_progress(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)

    try:
        types = json.loads(user.get("training_types") or "[]")
    except (TypeError, ValueError):
        types = []
    types_str = ", ".join(TRAINING_TYPES.get(t, t) for t in types) or "—"
    place_str = TRAINING_PLACES.get(user.get("training_place"), "—")
    weight_str = f"{user['weight']:g} кг" if user.get("weight") else "—"

    text = (
        f"📊 <b>Твой прогресс</b>\n\n"
        f"Уровень: {LEVELS.get(user['level'], '—')}\n"
        f"Вес: {weight_str}\n"
        f"Место тренировок: {place_str}\n"
        f"Вид тренировок: {types_str}\n"
        f"Обещание себе: «{user['promise']}»\n\n"
        f"🔥 Текущий стрик: <b>{user['streak']}</b> дн.\n"
        f"🏆 Лучший стрик: {user['longest_streak']} дн.\n"
        f"💪 Всего тренировок: {user['total_workouts']}"
    )

    # Блок персонажа только когда мини-апп снова включён
    if config.CHARACTER_ENABLED:
        stage = db.get_character_stage(user["streak"] or 0)
        next_line = (
            f"До следующей стадии персонажа: {stage['next_threshold'] - user['streak']} дн."
            if stage["next_threshold"] is not None
            else "Персонаж достиг максимальной стадии 🔥"
        )
        text += (
            f"\n\n🎮 Персонаж: <b>{stage['name']}</b>\n"
            f"{stage['description']}\n{next_line}"
        )

    await callback.message.edit_text(text, reply_markup=kb.back_to_menu_kb())
    await callback.answer()
