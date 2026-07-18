"""
Middleware, который перехватывает любые сообщения и нажатия кнопок от
заблокированных (за срыв стрика) пользователей и не пускает их дальше —
пока не оплатят штраф и админ не разблокирует командой /unlock.
"""

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

import config
import database as db


def blocked_text(user: dict) -> str:
    return (
        "🚫 <b>Доступ закрыт</b>\n"
        "Ты сорвал стрик и пока не оплатил штраф.\n\n"
        f"К оплате: <b>{config.PENALTY_TEXT}</b>\n"
        f"Оплати и напиши тренеру: {config.PAYMENT_LINK}\n\n"
        "Доступ откроют сразу после оплаты."
    )


class BlockCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_obj = getattr(event, "from_user", None)
        if user_obj is None:
            return await handler(event, data)

        telegram_id = user_obj.id

        # Админ никогда не блокируется, чтобы всегда мог управлять ботом
        # и разблокировать других (в т.ч. командой /unlock).
        if config.ADMIN_CHAT_ID and telegram_id == config.ADMIN_CHAT_ID:
            return await handler(event, data)

        user = await db.get_user(telegram_id)
        if user and user.get("blocked"):
            text = blocked_text(user)
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ заблокирован до оплаты", show_alert=True)
                try:
                    await event.message.answer(text)
                except Exception:
                    pass
            elif isinstance(event, Message):
                await event.answer(text)
            return

        return await handler(event, data)
