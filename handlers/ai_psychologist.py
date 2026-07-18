import logging

import aiohttp
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import keyboards as kb
from content import AI_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
router = Router()

HISTORY_LIMIT = 12  # сколько последних сообщений держим в контексте разговора


class AIPsych(StatesGroup):
    chatting = State()


@router.callback_query(F.data == "menu_ai_psych")
async def start_ai(callback: CallbackQuery, state: FSMContext):
    if not config.MISTRAL_API_KEY:
        await callback.message.edit_text(
            "🧠 ИИ-психолог пока не настроен — не хватает ключа Mistral API. Напиши тренеру напрямую.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    await state.set_state(AIPsych.chatting)
    await state.update_data(history=[])
    await callback.message.edit_text(
        "🧠 <b>ИИ-психолог</b>\n\n"
        "Я на связи. Расскажи, что тебя беспокоит — усталость, лень, нехватка времени, что угодно. "
        "Просто напиши сообщение текстом.\n\nЧтобы закончить разговор — нажми «Завершить».",
        reply_markup=kb.end_ai_kb(),
    )
    await callback.answer()


@router.message(AIPsych.chatting)
async def ai_message(message: Message, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": message.text})

    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:
        pass

    reply = await ask_mistral(history)
    history.append({"role": "assistant", "content": reply})

    await state.update_data(history=history[-HISTORY_LIMIT:])
    await message.answer(reply, reply_markup=kb.end_ai_kb())


@router.callback_query(AIPsych.chatting, F.data == "ai_end")
async def end_ai(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Хорошо 🤝 Я на связи, если снова понадоблюсь. А тренировки всё-таки не бросай — "
        "план и стрик никуда не делись.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()


async def ask_mistral(history: list) -> str:
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + history

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
            async with session.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.MISTRAL_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.warning(f"Mistral API вернул ошибку {resp.status}: {data}")
                    return "Извини, сейчас не получается ответить. Попробуй чуть позже 🙏"
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"Ошибка запроса к Mistral AI: {e}")
        return "Извини, что-то не так со связью. Попробуй написать ещё раз чуть позже 🙏"
