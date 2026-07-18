from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

import config
import database as db
import keyboards as kb
from content import LEVELS, TRAINING_PLACES

router = Router()

VALID_PLACES = list(TRAINING_PLACES.keys()) + ["all"]
VALID_LEVELS = list(LEVELS.keys()) + ["all"]


def _is_admin(user_id: int) -> bool:
    return bool(config.ADMIN_CHAT_ID and user_id == config.ADMIN_CHAT_ID)


# ---------------------------------------------------------------------------
# Подтверждение / отклонение тренировки по фото от клиента
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("admin_approve:"))
async def admin_approve_proof(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Только для админа", show_alert=True)
        return

    proof_id = int(callback.data.split(":")[1])
    proof = await db.get_proof(proof_id)
    if not proof:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if proof["verdict"] != "pending":
        await callback.answer(f"Уже обработано: {proof['verdict']}", show_alert=True)
        return

    telegram_id = proof["telegram_id"]

    if await db.has_logged_today(telegram_id):
        await db.update_proof_verdict(proof_id, "approved")
        await callback.answer("Тренировка уже была засчитана ранее")
        try:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + "\n\n✅ Уже было засчитано ранее",
                reply_markup=None,
            )
        except Exception:
            try:
                await callback.message.edit_text(
                    (callback.message.text or "") + "\n\n✅ Уже было засчитано ранее",
                    reply_markup=None,
                )
            except Exception:
                pass
        return

    await db.update_proof_verdict(proof_id, "approved")
    user = await db.mark_workout_complete(telegram_id)

    try:
        await bot.send_message(
            telegram_id,
            f"✅ Тренер засчитал тренировку!\n🔥 Стрик: {user['streak']} дн.",
            reply_markup=kb.back_to_menu_kb(),
        )
    except Exception:
        pass

    status = f"\n\n✅ <b>Засчитано</b> (стрик клиента: {user['streak']} дн.)"
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + status,
                reply_markup=None,
            )
        else:
            await callback.message.edit_text(
                (callback.message.text or "") + status,
                reply_markup=None,
            )
    except Exception:
        pass

    await callback.answer("Тренировка засчитана ✅")


@router.callback_query(F.data.startswith("admin_reject:"))
async def admin_reject_proof(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Только для админа", show_alert=True)
        return

    proof_id = int(callback.data.split(":")[1])
    proof = await db.get_proof(proof_id)
    if not proof:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if proof["verdict"] != "pending":
        await callback.answer(f"Уже обработано: {proof['verdict']}", show_alert=True)
        return

    await db.update_proof_verdict(proof_id, "rejected")
    telegram_id = proof["telegram_id"]

    try:
        await bot.send_message(
            telegram_id,
            "❌ Тренер не засчитал тренировку по этому фото.\n\n"
            "Пересними: должно быть видно, что ты реально тренировался "
            "(зал / дома, обстановка, по возможности жест дня). "
            "Потом снова нажми «📸 Подтвердить тренировку».",
            reply_markup=kb.back_to_menu_kb(),
        )
    except Exception:
        pass

    status = "\n\n❌ <b>Отклонено</b>"
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + status,
                reply_markup=None,
            )
        else:
            await callback.message.edit_text(
                (callback.message.text or "") + status,
                reply_markup=None,
            )
    except Exception:
        pass

    await callback.answer("Заявка отклонена")


@router.message(Command("pending"))
async def cmd_pending(message: Message, bot: Bot):
    """Список заявок на подтверждение тренировки, которые ещё ждут твоего решения."""
    if not _is_admin(message.from_user.id):
        return

    proofs = await db.get_pending_proofs(limit=20)
    if not proofs:
        await message.answer("Ожидающих заявок нет 🙌")
        return

    await message.answer(f"⏳ <b>Заявки на подтверждение:</b> {len(proofs)}\nПересылаю…")

    for p in proofs:
        user = await db.get_user(p["telegram_id"])
        username = f"@{user['username']}" if user and user.get("username") else "—"
        name = (user.get("name") if user else None) or "—"
        caption = (
            f"📸 Заявка #{p['id']}\n"
            f"Клиент: {name} ({username})\n"
            f"id: <code>{p['telegram_id']}</code>\n"
            f"Дата: {p['proof_date']}\n"
            f"Стрик: {(user or {}).get('streak') or 0}"
        )
        try:
            if p.get("file_id"):
                await bot.send_photo(
                    message.chat.id,
                    p["file_id"],
                    caption=caption,
                    reply_markup=kb.admin_proof_kb(p["id"]),
                )
            else:
                await message.answer(caption, reply_markup=kb.admin_proof_kb(p["id"]))
        except Exception:
            await message.answer(caption + "\n(не удалось прикрепить фото)", reply_markup=kb.admin_proof_kb(p["id"]))


@router.message(Command("unlock"))
async def cmd_unlock(message: Message, bot: Bot):
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /unlock <telegram_id>")
        return

    telegram_id = int(parts[1])
    user = await db.get_user(telegram_id)
    if not user:
        await message.answer("Такого пользователя нет в базе.")
        return

    await db.unblock_user(telegram_id)
    await message.answer(f"Пользователь {telegram_id} разблокирован ✅")

    try:
        await bot.send_message(
            telegram_id,
            "✅ Оплата получена, доступ к боту восстановлен.\n"
            "Возвращайся в игру — стрик начинается заново 💪",
            reply_markup=kb.main_menu_kb(),
        )
    except Exception:
        pass


@router.message(Command("blocked"))
async def cmd_blocked(message: Message):
    if not _is_admin(message.from_user.id):
        return

    users = await db.get_blocked_users()
    if not users:
        await message.answer("Заблокированных нет 🙌")
        return

    lines = ["🚫 <b>Заблокированные пользователи</b>\n"]
    for u in users:
        username = f"@{u['username']}" if u.get("username") else "—"
        lines.append(f"id {u['telegram_id']} ({username}) — с {u.get('blocked_at', '—')}")
    lines.append(f"\nШтраф за срыв: {config.PENALTY_TEXT}\nРазблокировать: /unlock <id>")
    await message.answer("\n".join(lines))


@router.message(Command("addmaterial"))
async def cmd_addmaterial(message: Message):
    """Использование: ответь на фото или видео командой
    /addmaterial <место|all> <уровень|all> <подпись...>
    место: home / gym / all
    уровень: beginner / intermediate / advanced / all
    """
    if not _is_admin(message.from_user.id):
        return

    if not message.reply_to_message or not (
        message.reply_to_message.photo or message.reply_to_message.video
    ):
        await message.answer(
            "Ответь этой командой на сообщение с фото или видео.\n\n"
            "Формат: /addmaterial <место|all> <уровень|all> <подпись>\n"
            "место: home / gym / all\n"
            "уровень: beginner / intermediate / advanced / all\n\n"
            "Пример: /addmaterial home beginner Техника приседаний"
        )
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer(
            "Не хватает параметров. Формат: /addmaterial <место|all> <уровень|all> <подпись>"
        )
        return

    place = parts[1].lower()
    level = parts[2].lower()
    caption = parts[3] if len(parts) > 3 else ""

    if place not in VALID_PLACES:
        await message.answer(f"Место должно быть одним из: {', '.join(VALID_PLACES)}")
        return
    if level not in VALID_LEVELS:
        await message.answer(f"Уровень должен быть одним из: {', '.join(VALID_LEVELS)}")
        return

    src = message.reply_to_message
    if src.video:
        media_type = "video"
        file_id = src.video.file_id
    else:
        media_type = "photo"
        file_id = src.photo[-1].file_id

    await db.add_material(place, level, media_type, file_id, caption)
    await message.answer(
        f"Материал добавлен ✅\nМесто: {place} | Уровень: {level} | Тип: {media_type}"
    )
