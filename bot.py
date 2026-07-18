import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

import config
from database import init_db
from handlers import register_all_handlers
from scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def setup_commands(bot: Bot):
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать / перезапустить"),
            BotCommand(command="menu", description="Главное меню"),
        ],
        scope=BotCommandScopeDefault(),
    )

    if config.ADMIN_CHAT_ID:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Начать"),
                    BotCommand(command="menu", description="Главное меню"),
                    BotCommand(command="pending", description="Заявки на подтверждение тренировок"),
                    BotCommand(command="unlock", description="Разблокировать <id> после оплаты"),
                    BotCommand(command="blocked", description="Список заблокированных"),
                    BotCommand(command="addmaterial", description="Добавить фото/видео (ответом на файл)"),
                ],
                scope=BotCommandScopeChat(chat_id=config.ADMIN_CHAT_ID),
            )
        except Exception as e:
            logger.warning("Не удалось задать команды для админа: %s", e)


async def main():
    await init_db()
    logger.info("База данных готова: %s", config.DB_PATH)

    # Каталог видео sportkuznica + привязка к библиотеке упражнений
    try:
        import video_catalog as vc
        from content import EXERCISE_LIBRARY, _load_training_plans

        # Прогрев JSON (локально или fallback с GitHub, если data/ не на хостинге)
        plans = _load_training_plans()
        logger.info("Планы тренировок: categories_loaded=%s", bool(plans))

        stats = vc.catalog_stats()
        if stats["total"] == 0:
            # повторная попытка force-load (на случай гонки/первого fail)
            vc.load_catalog(force=True)
            stats = vc.catalog_stats()
        bound = vc.bind_library_videos(EXERCISE_LIBRARY)
        logger.info(
            "Каталог видео: %s упражнений, с ссылкой: %s; привязано к библиотеке: %s; path=%s",
            stats["total"],
            stats["with_video"],
            bound,
            stats.get("path"),
        )
        if stats["total"] == 0:
            logger.error(
                "Каталог видео ПУСТ. Проверь data/sportkuznica_exercises.json "
                "или доступ в интернет для fallback GitHub."
            )
    except Exception as e:
        logger.exception("Каталог видео не загрузился: %s", e)

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    register_all_handlers(dp)
    await setup_commands(bot)

    setup_scheduler(bot, config.REMINDER_HOUR)
    logger.info(
        "Планировщик: час напоминания=%s, timezone=%s",
        config.REMINDER_HOUR,
        config.TIMEZONE,
    )

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен (polling). Останови через Ctrl+C.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
