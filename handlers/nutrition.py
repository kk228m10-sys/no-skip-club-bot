import json

from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
from content import NUTRITION_TIPS, TRAINING_TYPES, calculate_kbju

router = Router()


@router.callback_query(F.data == "menu_nutrition")
async def menu_nutrition(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    try:
        types = json.loads(user.get("training_types") or "[]")
    except (TypeError, ValueError):
        types = []
    default_type = types[0] if types else None

    if default_type in NUTRITION_TIPS:
        await send_nutrition(callback, default_type)
        return

    await callback.message.edit_text(
        "🥗 Питание. Под какой вид тренировок показать рекомендации?",
        reply_markup=kb.nutrition_goals_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("nutr:"))
async def nutrition_by_goal(callback: CallbackQuery):
    goal = callback.data.split(":")[1]
    await send_nutrition(callback, goal)


async def send_nutrition(callback: CallbackQuery, goal: str):
    user = await db.get_user(callback.from_user.id)
    weight = user.get("weight") if user else None

    tips = NUTRITION_TIPS.get(goal, NUTRITION_TIPS["ofp"])
    text = f"🥗 <b>Питание — {TRAINING_TYPES.get(goal, '')}</b>\n\n" + "\n\n".join(f"• {t}" for t in tips)

    if weight:
        kbju = calculate_kbju(weight, goal)
        text += (
            f"\n\n🔢 <b>Твоя примерная норма КБЖУ</b> "
            f"(вес {weight:g} кг, программа «{TRAINING_TYPES.get(goal, '')}»):\n"
            f"Калории: ~{kbju['calories']} ккал\n"
            f"Белки: ~{kbju['protein']} г\n"
            f"Жиры: ~{kbju['fat']} г\n"
            f"Углеводы: ~{kbju['carbs']} г\n\n"
            "Это ориентировочный расчёт по весу и виду тренировок, а не точная "
            "медицинская норма."
        )
    else:
        text += (
            "\n\nНе получилось посчитать КБЖУ — в профиле не указан вес. "
            "Пройди онбординг заново, чтобы бот его сохранил."
        )

    text += (
        "\n\n⚠️ Это общие рекомендации, не медицинское назначение. "
        "При особых состояниях здоровья — советуйся с врачом или диетологом."
    )
    await callback.message.edit_text(text, reply_markup=kb.back_to_menu_kb())
    await callback.answer()
