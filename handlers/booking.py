import datetime

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import config
import database as db
import keyboards as kb
from content import BOOKING_DAYS, BOOKING_SLOTS, MAX_BOOKING_PER_SLOT

router = Router()

WEEKS_AHEAD_PER_DAY = 1  # показываем только ближайшую дату каждого дня (среда/суббота);
# при пересчёте от today() список сам сдвигается вперёд по календарю после
# наступления/прохождения даты, отдельно хранить конкретные даты не нужно.


async def build_slots_data():
    today = datetime.date.today()
    now = datetime.datetime.now().time()

    dates = []
    for weekday, label in BOOKING_DAYS.items():
        found = 0
        d = today
        while found < WEEKS_AHEAD_PER_DAY:
            if d.weekday() == weekday:
                dates.append((d, label))
                found += 1
            d += datetime.timedelta(days=1)
    dates.sort(key=lambda x: x[0])

    slots_data = []
    for d, label in dates:
        for idx, slot in enumerate(BOOKING_SLOTS):
            start_str = slot.split("-")[0]
            start_h, start_m = map(int, start_str.split(":"))
            if d == today and now >= datetime.time(start_h, start_m):
                continue  # слот на сегодня уже начался/прошёл

            count = await db.count_bookings(d.isoformat(), slot)
            slots_data.append(
                {
                    "date": d,
                    "label": label,
                    "slot": slot,
                    "slot_idx": idx,
                    "count": count,
                    "full": count >= MAX_BOOKING_PER_SLOT,
                }
            )
    return slots_data


@router.callback_query(F.data == "menu_booking")
async def menu_booking(callback: CallbackQuery):
    slots_data = await build_slots_data()

    if not slots_data:
        await callback.message.edit_text(
            "Свободных слотов пока нет, загляни чуть позже.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📅 <b>Запись на онлайн-встречу</b>\n\n"
        "Созвоны проходят по средам и субботам, с 17:00 до 20:00, часовыми слотами. "
        f"Максимум {MAX_BOOKING_PER_SLOT} человек на один слот.\n\n"
        "Выбери удобное время:",
        reply_markup=kb.booking_slots_kb(slots_data),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("book:"))
async def book_slot(callback: CallbackQuery, bot: Bot):
    _, date_iso, idx_str = callback.data.split(":")
    idx = int(idx_str)
    slot = BOOKING_SLOTS[idx]
    d = datetime.date.fromisoformat(date_iso)
    day_label = BOOKING_DAYS.get(d.weekday(), "")

    count = await db.count_bookings(date_iso, slot)
    if count >= MAX_BOOKING_PER_SLOT:
        await callback.answer("На это время мест больше нет 😔", show_alert=True)
        return

    already = await db.get_user_booking(callback.from_user.id, date_iso, slot)
    if already:
        await callback.answer("Ты уже записан на это время", show_alert=True)
        return

    username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
    await db.add_booking(callback.from_user.id, username, date_iso, slot)
    new_count = await db.count_bookings(date_iso, slot)

    await callback.message.edit_text(
        f"✅ Записал тебя: {day_label} {d.strftime('%d.%m')}, {slot}.\nЖду на созвоне!",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()

    if config.ADMIN_CHAT_ID:
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                "📅 <b>Новая запись на созвон</b>\n"
                f"{username} (id {callback.from_user.id})\n"
                f"{day_label} {d.strftime('%d.%m')}, {slot}\n"
                f"Занято мест: {new_count}/{MAX_BOOKING_PER_SLOT}",
            )
        except Exception:
            pass


@router.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    bookings = await db.get_user_bookings(callback.from_user.id)

    if not bookings:
        await callback.message.edit_text(
            "У тебя пока нет активных записей.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    items = []
    for b in bookings:
        d = datetime.date.fromisoformat(b["booking_date"])
        items.append(
            {
                "id": b["id"],
                "label": BOOKING_DAYS.get(d.weekday(), ""),
                "date_str": d.strftime("%d.%m"),
                "slot": b["slot"],
            }
        )

    lines = ["📋 <b>Твои записи</b>\n"]
    for it in items:
        lines.append(f"• {it['label']} {it['date_str']}, {it['slot']}")

    await callback.message.edit_text("\n".join(lines), reply_markup=kb.my_bookings_kb(items))
    await callback.answer()


@router.callback_query(F.data.startswith("cancelbook:"))
async def cancel_booking_handler(callback: CallbackQuery, bot: Bot):
    booking_id = int(callback.data.split(":")[1])
    await db.cancel_booking(booking_id, callback.from_user.id)
    await callback.answer("Запись отменена")

    if config.ADMIN_CHAT_ID:
        username = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
        try:
            await bot.send_message(
                config.ADMIN_CHAT_ID,
                f"❌ {username} (id {callback.from_user.id}) отменил запись на созвон.",
            )
        except Exception:
            pass

    await my_bookings(callback)
