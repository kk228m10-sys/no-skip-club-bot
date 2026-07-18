"""
Подтверждение тренировки: клиент присылает фото → админ получает уведомление
и сам засчитывает или отклоняет заявку.
"""

import datetime
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import database as db
import keyboards as kb
from content import DAYS_RU

logger = logging.getLogger(__name__)
router = Router()


class ConfirmPhoto(StatesGroup):
    waiting_photo = State()


async def _today_is_rest_day(telegram_id: int) -> bool:
    """True, если сегодня по плану пользователя — день отдыха (или плана нет вообще)."""
    plan_row = await db.get_current_weekly_plan(telegram_id)
    if not plan_row or not plan_row.get("plan"):
        return False  # плана ещё нет — не блокируем, пусть отправит фото как раньше
    today_name = DAYS_RU[datetime.date.today().weekday()]
    day_data = plan_row["plan"].get(today_name, {})
    return bool(day_data.get("rest", True))


@router.callback_query(F.data == "menu_confirm_photo")
async def menu_confirm_photo(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    if await _today_is_rest_day(telegram_id):
        await callback.message.edit_text(
            "💤 Сегодня день отдыха по твоему плану — подтверждать нечего.\n"
            "Фото принимается только в тренировочные дни.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    if await db.has_logged_today(telegram_id):
        await callback.message.edit_text(
            "Сегодняшняя тренировка уже отмечена ✅", reply_markup=kb.back_to_menu_kb()
        )
        await callback.answer()
        return

    if await db.has_pending_proof_today(telegram_id):
        await callback.message.edit_text(
            "⏳ Твоя заявка на подтверждение уже отправлена тренеру.\n"
            "Жди решения — как только засчитают, стрик обновится.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    if not config.ADMIN_CHAT_ID:
        await callback.message.edit_text(
            "Подтверждение через тренера пока не настроено (нет ADMIN_CHAT_ID).\n"
            "Напиши тренеру напрямую.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    today_iso = datetime.date.today().isoformat()
    challenge = await db.get_daily_challenge(today_iso)

    await state.set_state(ConfirmPhoto.waiting_photo)

    if challenge:
        hint = (
            f"Жест дня (по желанию): {challenge['emoji']} <b>{challenge['name']}</b>\n\n"
            f"Сделай фото в зале или дома — желательно с этим жестом и так, чтобы было видно "
            f"обстановку (тренажёры, коврик и т.п.)."
        )
    else:
        hint = (
            "Сделай фото в зале или дома, где ты тренировался — "
            "чтобы тренер видел, что тренировка реально была."
        )

    await callback.message.edit_text(
        f"📸 <b>Подтверди тренировку</b>\n\n"
        f"{hint}\n\n"
        f"Пришли фото одним сообщением. Тренер получит его и сам засчитает тренировку.",
    )
    await callback.answer()


@router.message(ConfirmPhoto.waiting_photo, F.photo)
async def confirm_photo_received(message: Message, state: FSMContext, bot: Bot):
    telegram_id = message.from_user.id

    if await _today_is_rest_day(telegram_id):
        await message.answer(
            "💤 Сегодня день отдыха по твоему плану — подтверждать нечего.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await state.clear()
        return

    if await db.has_logged_today(telegram_id):
        await message.answer(
            "Тренировка уже была отмечена сегодня ✅", reply_markup=kb.back_to_menu_kb()
        )
        await state.clear()
        return

    if await db.has_pending_proof_today(telegram_id):
        await message.answer(
            "⏳ Заявка уже на проверке у тренера. Жди решения.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await state.clear()
        return

    today_iso = datetime.date.today().isoformat()
    challenge = await db.get_daily_challenge(today_iso)
    gesture_key = challenge["gesture_key"] if challenge else "none"
    file_id = message.photo[-1].file_id

    proof_id = await db.save_proof(telegram_id, today_iso, gesture_key, file_id, "pending")
    await state.clear()

    user = await db.get_user(telegram_id)
    username = f"@{user['username']}" if user and user.get("username") else "—"
    name = (user.get("name") if user else None) or message.from_user.full_name or "—"
    gesture_line = ""
    if challenge:
        gesture_line = f"Жест дня: {challenge['emoji']} {challenge['name']}\n"

    caption = (
        f"📸 <b>Заявка на подтверждение тренировки</b>\n\n"
        f"Клиент: {name} ({username})\n"
        f"id: <code>{telegram_id}</code>\n"
        f"{gesture_line}"
        f"Дата: {today_iso}\n"
        f"Стрик сейчас: {(user or {}).get('streak') or 0} дн.\n\n"
        f"Засчитай, если тренировка реально была."
    )

    try:
        await bot.send_photo(
            config.ADMIN_CHAT_ID,
            file_id,
            caption=caption,
            reply_markup=kb.admin_proof_kb(proof_id),
        )
    except Exception as e:
        logger.warning("Не удалось отправить фото админу: %s", e)
        # fallback — текст без фото
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                caption + f"\n\n(фото file_id: <code>{file_id}</code>)",
                reply_markup=kb.admin_proof_kb(proof_id),
            )
        except Exception as e2:
            logger.warning("Не удалось отправить заявку админу: %s", e2)
            await message.answer(
                "Не удалось отправить заявку тренеру. Попробуй ещё раз позже или напиши напрямую.",
                reply_markup=kb.back_to_menu_kb(),
            )
            await db.update_proof_verdict(proof_id, "error")
            return

    await message.answer(
        "✅ Фото отправлено тренеру на проверку.\n"
        "Как только засчитают — придёт уведомление и стрик обновится.",
        reply_markup=kb.back_to_menu_kb(),
    )


@router.message(ConfirmPhoto.waiting_photo)
async def confirm_photo_wrong_type(message: Message):
    await message.answer("Жду именно фото 📸 — пришли его одним сообщением (не файлом/документом).")
