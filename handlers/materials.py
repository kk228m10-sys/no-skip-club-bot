from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

import database as db
import keyboards as kb
import video_catalog as vc
from content import EXERCISE_LIBRARY, LEVELS, TRAINING_PLACES, TRAINING_TYPES

router = Router()


class VideoSearch(StatesGroup):
    waiting_query = State()


def _user_place_level(user: dict):
    place = user.get("training_place") or "home"
    level = user.get("level") or "beginner"
    return place, level


def _video_results_kb(results: list[dict], prefix: str = "vid"):
    rows = []
    for item in results[:10]:
        title = (item.get("title") or "Упражнение")[:40]
        rows.append(
            [InlineKeyboardButton(text=f"▶️ {title}", callback_data=f"{prefix}:{item['id']}")]
        )
    rows.append([InlineKeyboardButton(text="🔍 Другой поиск", callback_data="menu_videos")])
    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _video_detail_kb(item_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Искать ещё", callback_data="menu_videos")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")],
        ]
    )


@router.callback_query(F.data == "menu_exercises")
async def menu_exercises(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    place, level = _user_place_level(user)
    exercises = EXERCISE_LIBRARY.get(place, {}).get(level, [])

    lines = [
        f"📋 <b>Упражнения и техника — {TRAINING_PLACES.get(place, place)}, "
        f"{LEVELS.get(level, level)}</b>\n"
    ]
    for ex in exercises:
        types_str = ", ".join(TRAINING_TYPES.get(t, t) for t in ex.get("types", []))
        lines.append(f"• <b>{ex['name']}</b> ({ex['sets']}) — {types_str}\n  {ex['technique']}")

        url = ex.get("video_url")
        if not url:
            video = vc.find_video(ex["name"], place=place)
            url = video.get("video_url") if video else None
        if url:
            lines.append(f"  ▶️ <a href=\"{url}\">Видео техники</a>")

    lines.append(
        "\nЭто библиотека под твой текущий уровень и место тренировок. "
        "Если поменяешь их в «⚙️ Изменить план» — список обновится сам.\n"
        "Полный каталог видео — кнопка «🎬 Видео упражнений»."
    )

    await callback.message.edit_text(
        "\n\n".join(lines),
        reply_markup=kb.back_to_menu_kb(),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "menu_videos")
async def menu_videos(callback: CallbackQuery, state: FSMContext):
    stats = vc.catalog_stats()
    if stats["total"] == 0:
        await callback.message.edit_text(
            "🎬 <b>Видео упражнений</b>\n\n"
            "Каталог ещё не загружен. Скажи тренеру — нужно запустить сбор с sportkuznica.com.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    await state.set_state(VideoSearch.waiting_query)
    await callback.message.edit_text(
        f"🎬 <b>Видео упражнений</b>\n\n"
        f"В каталоге: <b>{stats['total']}</b> упражнений "
        f"(с видео: {stats['with_video']}).\n"
        f"Источник: sportkuznica.com\n\n"
        f"Напиши название упражнения (например: «отжимания», «присед», «махи гирей») "
        f"— пришлю ссылку на технику.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Видео для дома", callback_data="vid_place:home")],
                [InlineKeyboardButton(text="🏋️ Видео для зала", callback_data="vid_place:gym")],
                [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("vid_place:"))
async def videos_by_place(callback: CallbackQuery, state: FSMContext):
    place = callback.data.split(":")[1]
    await state.clear()
    items = vc.list_for_place(place, limit=12)
    if not items:
        await callback.message.edit_text(
            "Пока нет роликов с этим тегом. Попробуй поиск по названию.",
            reply_markup=kb.back_to_menu_kb(),
        )
        await callback.answer()
        return

    place_name = TRAINING_PLACES.get(place, place)
    await callback.message.edit_text(
        f"🎬 Видео — <b>{place_name}</b>\nВыбери упражнение:",
        reply_markup=_video_results_kb(items),
    )
    await callback.answer()


@router.message(VideoSearch.waiting_query, F.text)
async def video_search_query(message: Message, state: FSMContext):
    query = (message.text or "").strip()
    if not query or query == "☰ Меню":
        await state.clear()
        await message.answer("Главное меню:", reply_markup=kb.main_menu_kb())
        return

    user = await db.get_user(message.from_user.id)
    place = (user or {}).get("training_place")
    results = vc.search(query, limit=10, place=place)
    if not results:
        results = vc.search(query, limit=10, place=None)

    await state.clear()
    if not results:
        await message.answer(
            f"По запросу «{query}» ничего не нашёл.\n"
            "Попробуй короче: «присед», «тяг», «бёрпи», «жим».",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Искать ещё", callback_data="menu_videos")],
                    [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")],
                ]
            ),
        )
        return

    await message.answer(
        f"Нашёл по «{query}» — выбери упражнение:",
        reply_markup=_video_results_kb(results),
    )


@router.callback_query(F.data.startswith("vid:"))
async def video_detail(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = callback.data.split(":", 1)[1]
    item = vc.get_by_id(item_id)
    if not item:
        await callback.answer("Видео не найдено", show_alert=True)
        return

    await callback.message.edit_text(
        vc.format_video_card(item),
        reply_markup=_video_detail_kb(item_id),
        disable_web_page_preview=False,
    )
    await callback.answer()


@router.callback_query(F.data == "menu_media")
async def menu_media(callback: CallbackQuery, bot: Bot):
    user = await db.get_user(callback.from_user.id)
    place, level = _user_place_level(user)
    materials = await db.get_materials(place, level)

    if not materials:
        # fallback — каталог видео со sportkuznica
        stats = vc.catalog_stats()
        if stats["total"]:
            await callback.message.edit_text(
                "🎥 <b>Материалы</b>\n\n"
                "Свои фото/видео тренера пока не добавлены.\n"
                f"Но есть каталог техники: <b>{stats['with_video']}</b> видео с sportkuznica.com.\n\n"
                "Открой «🎬 Видео упражнений» или нажми кнопку ниже.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🎬 Видео упражнений", callback_data="menu_videos")],
                        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu_back")],
                    ]
                ),
            )
        else:
            await callback.message.edit_text(
                "🎥 <b>Материалы</b>\n\n"
                "Фото и видео для твоего уровня и места тренировок пока не добавлены. "
                "Загляни сюда позже — тренер обязательно что-то добавит.",
                reply_markup=kb.back_to_menu_kb(),
            )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"🎥 <b>Материалы — {TRAINING_PLACES.get(place, place)}, {LEVELS.get(level, level)}</b>\n\n"
        f"Отправляю {len(materials)} материал(ов) ⬇️",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()

    for m in materials:
        caption = m.get("caption") or ""
        try:
            if m["media_type"] == "photo":
                await bot.send_photo(callback.from_user.id, m["file_id"], caption=caption)
            elif m["media_type"] == "video":
                await bot.send_video(callback.from_user.id, m["file_id"], caption=caption)
        except Exception:
            continue
