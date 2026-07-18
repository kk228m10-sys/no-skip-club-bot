"""
Ежедневные задачи:
1. Утром в REMINDER_HOUR — напоминание всем, у кого сегодня тренировочный день
   (заблокированным за срыв стрика напоминание не шлём — им нужно сперва
   оплатить штраф).
2. Поздно вечером — проверка: если тренировочный день прошёл, а тренировка
   не отмечена, стрик обнуляется, пользователь блокируется до оплаты штрафа,
   ему приходит сообщение со ссылкой на оплату, а админу — кто и сколько
   должен.
"""

import datetime
import logging
import random
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import database as db
from content import DAYS_RU, GESTURES

logger = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(config.TIMEZONE)
    except Exception:
        logger.warning("Неизвестный TIMEZONE=%s, использую Asia/Almaty", config.TIMEZONE)
        return ZoneInfo("Asia/Almaty")


def local_today() -> datetime.date:
    """Сегодняшняя дата в часовом поясе бота (не UTC сервера)."""
    return datetime.datetime.now(_tz()).date()


async def get_or_create_daily_challenge():
    today_iso = local_today().isoformat()
    challenge = await db.get_daily_challenge(today_iso)
    if challenge:
        return challenge
    gesture = random.choice(GESTURES)
    return await db.create_daily_challenge(today_iso, gesture["key"], gesture["emoji"], gesture["name"])


async def send_reminders(bot: Bot):
    today_name = DAYS_RU[local_today().weekday()]
    users = await db.get_all_users()

    challenge = None
    for user in users:
        if user.get("blocked"):
            continue

        plan_row = await db.get_current_weekly_plan(user["telegram_id"])
        if not plan_row:
            continue
        day_data = plan_row["plan"].get(today_name, {})
        if day_data.get("rest", True):
            continue

        already_done = await db.has_logged_today(user["telegram_id"])
        if already_done:
            continue

        if challenge is None:
            challenge = await get_or_create_daily_challenge()

        try:
            await bot.send_message(
                user["telegram_id"],
                f"🔥 Сегодня {today_name.lower()} — день тренировки.\n"
                f"Стрик: {user['streak']} дн. Не дай ему прерваться.\n\n"
                f"📸 Жест дня: {challenge['emoji']} <b>{challenge['name']}</b>\n"
                f"После тренировки сделай фото (желательно с этим жестом) на фоне зала или дома "
                f"и пришли через «📸 Подтвердить тренировку» в меню — обязательно до 23:00. "
                f"Тренер получит фото и сам засчитает тренировку.",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить напоминание {user['telegram_id']}: {e}")


async def check_missed_workouts(bot: Bot):
    """Дедлайн подтверждения тренировки — 23:00. Если сегодня был тренировочный
    день и пользователь до 23:00 не прислал фото (и оно не одобрено) —
    сбрасываем стрик, блокируем доступ к боту и уведомляем пользователя и
    админа. Отправленное но ещё не проверенное тренером фото (pending)
    дедлайн уже закрывает — блокировать за медленную проверку тренера нельзя,
    это ответственность клиента только за то, что он сам должен успеть."""
    today_name = DAYS_RU[local_today().weekday()]
    users = await db.get_all_users()

    for user in users:
        telegram_id = user["telegram_id"]

        if user.get("blocked"):
            continue

        plan_row = await db.get_current_weekly_plan(telegram_id)
        if not plan_row:
            continue
        day_data = plan_row["plan"].get(today_name, {})
        if day_data.get("rest", True):
            continue

        already_done = await db.has_logged_today(telegram_id)
        if already_done:
            continue

        pending = await db.has_pending_proof_today(telegram_id)
        if pending:
            continue  # фото прислано вовремя, ждём проверки тренера — не блокируем

        await db.reset_streak(telegram_id)
        await db.block_user(telegram_id)
        logger.info(f"Пользователь {telegram_id} заблокирован — пропущен {today_name}")

        try:
            await bot.send_message(
                telegram_id,
                "🚫 <b>Стрик сорван</b>\n"
                f"Ты не прислал фото-подтверждение тренировки за {today_name.lower()} до 23:00, "
                "и по правилам клуба доступ к боту закрыт до оплаты.\n\n"
                f"К оплате: <b>{config.PENALTY_TEXT}</b>\n\n"
                f"Оплати и напиши тренеру, чтобы разблокировали доступ: {config.PAYMENT_LINK}",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о блокировке {telegram_id}: {e}")

        if config.ADMIN_CHAT_ID:
            username = f"@{user['username']}" if user.get("username") else f"id {telegram_id}"
            try:
                await bot.send_message(
                    config.ADMIN_CHAT_ID,
                    "⚠️ <b>Срыв стрика</b>\n"
                    f"Пользователь: {username} (id {telegram_id})\n"
                    f"Пропущен день: {today_name} (фото не прислано до 23:00)\n"
                    f"К оплате: {config.PENALTY_TEXT}\n\n"
                    f"После получения оплаты разблокируй командой: /unlock {telegram_id}",
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление админу о {telegram_id}: {e}")


async def send_deadline_warning(bot: Bot):
    """За 2 часа до дедлайна (21:00) — последнее напоминание тем, кто ещё не
    прислал фото за сегодняшний тренировочный день."""
    today_name = DAYS_RU[local_today().weekday()]
    users = await db.get_all_users()

    for user in users:
        if user.get("blocked"):
            continue

        plan_row = await db.get_current_weekly_plan(user["telegram_id"])
        if not plan_row:
            continue
        day_data = plan_row["plan"].get(today_name, {})
        if day_data.get("rest", True):
            continue

        if await db.has_logged_today(user["telegram_id"]):
            continue
        if await db.has_pending_proof_today(user["telegram_id"]):
            continue

        try:
            await bot.send_message(
                user["telegram_id"],
                "⏰ <b>Последнее напоминание</b>\n"
                "Дедлайн подтверждения тренировки сегодня — 23:00.\n"
                "Не пришлёшь фото до этого времени — стрик сгорит и доступ к боту закроется.\n\n"
                "Жми «📸 Подтвердить тренировку» в меню.",
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить дедлайн-напоминание {user['telegram_id']}: {e}")


def setup_scheduler(bot: Bot, reminder_hour: int) -> AsyncIOScheduler:
    tz = _tz()
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(send_reminders, "cron", hour=reminder_hour, minute=0, args=[bot], timezone=tz)
    scheduler.add_job(send_deadline_warning, "cron", hour=21, minute=0, args=[bot], timezone=tz)
    scheduler.add_job(check_missed_workouts, "cron", hour=23, minute=0, args=[bot], timezone=tz)
    scheduler.start()
    logger.info("Планировщик: timezone=%s, reminder=%s:00", config.TIMEZONE, reminder_hour)
    return scheduler
