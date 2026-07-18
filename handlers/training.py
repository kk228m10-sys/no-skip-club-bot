import datetime
import json

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

import database as db
import keyboards as kb
import video_catalog as vc
from content import DAYS_RU, REST_DAY_TIP, TRAINING_TYPES, MAX_TRAINING_TYPES, generate_weekly_plan

router = Router()


class ChangeTypes(StatesGroup):
    waiting_types = State()


def _video_for_exercise(ex: dict, place: str | None = None):
    """Сначала video_url из упражнения (уже привязан), иначе поиск в каталоге."""
    if ex.get("video_url"):
        return {"video_url": ex["video_url"], "title": ex.get("video_title") or ex["name"]}
    return vc.find_video(ex["name"], place=place)


def format_day_plan(day_name: str, day_data: dict, place: str | None = None) -> str:
    if day_data.get("rest"):
        return f"📅 <b>{day_name}</b>\nДень отдыха.\n{REST_DAY_TIP}"

    lines = [f"📅 <b>{day_name}</b> — день тренировки\n"]
    for ex in day_data["exercises"]:
        block = f"• <b>{ex['name']}</b> — {ex['sets']}\n  {ex['technique']}"
        video = _video_for_exercise(ex, place=place)
        if video and video.get("video_url"):
            block += f"\n  ▶️ <a href=\"{video['video_url']}\">Видео техники</a>"
        lines.append(block)
    return "\n\n".join(lines)


def _user_place_and_types(user: dict):
    place = user.get("training_place") or "home"
    try:
        types = json.loads(user.get("training_types") or "[]")
    except (TypeError, ValueError):
        types = []
    if not types:
        types = ["ofp"]
    return place, types


async def get_or_refresh_plan(telegram_id: int, level: str, training_days_raw, days_per_week: int, place: str, training_types: list):
    plan_row = await db.get_current_weekly_plan(telegram_id)
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())

    if not plan_row or plan_row["week_start"] < week_start.isoformat():
        # план устарел (новая неделя) — генерируем новый под текущий уровень/место/виды
        training_days = json.loads(training_days_raw) if training_days_raw else None
        plan = generate_weekly_plan(level, place, training_types, training_days=training_days, days_per_week=days_per_week)
        await db.save_weekly_plan(telegram_id, week_start.isoformat(), plan)
        return plan

    return plan_row["plan"]


@router.callback_query(F.data == "menu_plan")
async def menu_plan(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    place, training_types = _user_place_and_types(user)
    plan = await get_or_refresh_plan(
        callback.from_user.id, user["level"], user.get("training_days"), user["days_per_week"], place, training_types
    )

    today_idx = datetime.date.today().weekday()
    today_name = DAYS_RU[today_idx]
    today_data = plan[today_name]

    already_done = await db.has_logged_today(callback.from_user.id)
    has_exercises = bool(today_data.get("exercises")) and not today_data.get("rest")

    text = format_day_plan(today_name, today_data, place=place)
    if already_done:
        text += "\n\n✅ Сегодняшняя тренировка уже отмечена. Так держать."
        markup = kb.plan_rest_kb(include_videos=has_exercises)
    elif today_data.get("rest"):
        markup = kb.back_to_menu_kb()
    else:
        markup = kb.workout_done_kb(include_videos=has_exercises)

    # добавим краткий обзор недели
    week_overview = "\n".join(
        f"{'💤' if plan[d]['rest'] else '🏋️'} {d}" for d in DAYS_RU
    )
    text += f"\n\n<b>Неделя целиком:</b>\n{week_overview}"

    await callback.message.edit_text(
        text, reply_markup=markup, disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "plan_today_videos")
async def plan_today_videos(callback: CallbackQuery):
    """Скидывает клиенту карточки с видео техники по каждому упражнению сегодня."""
    user = await db.get_user(callback.from_user.id)
    place, training_types = _user_place_and_types(user)
    plan = await get_or_refresh_plan(
        callback.from_user.id, user["level"], user.get("training_days"), user["days_per_week"], place, training_types
    )

    today_name = DAYS_RU[datetime.date.today().weekday()]
    today_data = plan.get(today_name) or {}
    exercises = today_data.get("exercises") or []

    if today_data.get("rest") or not exercises:
        await callback.answer("Сегодня день отдыха — упражнений нет", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        f"🎬 <b>Видео техники — {today_name}</b>\n"
        f"Ниже по каждому упражнению из сегодняшнего плана:"
    )

    found = 0
    for ex in exercises:
        video = _video_for_exercise(ex, place=place)
        if not video or not video.get("video_url"):
            await callback.message.answer(
                f"• <b>{ex['name']}</b>\n"
                f"Видео пока не найдено. Поищи вручную: «🎬 Видео упражнений»."
            )
            continue

        found += 1
        title = video.get("title") or ex["name"]
        caption = (
            f"▶️ <b>{ex['name']}</b> — {ex.get('sets', '')}\n"
            f"{ex.get('technique', '')}\n\n"
            f"Видео: {title}\n"
            f"{video['video_url']}"
        )
        await callback.message.answer(caption, disable_web_page_preview=False)

    if found:
        await callback.message.answer(
            f"Готово: {found} из {len(exercises)} с видео.\n"
            "После тренировки — «📸 Подтвердить тренировку».",
            reply_markup=kb.workout_done_kb(include_videos=False),
        )
    else:
        await callback.message.answer(
            "Автоматически видео не нашлись. Открой «🎬 Видео упражнений» и найди по названию.",
            reply_markup=kb.back_to_menu_kb(),
        )


@router.callback_query(F.data == "workout_done")
async def workout_done(callback: CallbackQuery):
    """Раньше можно было отметить без фото — теперь только через подтверждение тренером."""
    await callback.message.edit_text(
        "Тренировку засчитывает только тренер по фото.\n"
        "Нажми «📸 Подтвердить тренировку» и пришли снимок.",
        reply_markup=kb.workout_done_kb(include_videos=False),
    )
    await callback.answer()


# ---------------------------------------------------------------------------
# Смена / совмещение видов тренировок (не более двух) из главного меню.
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "menu_change_types")
async def menu_change_types(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    try:
        current = set(json.loads(user.get("training_types") or "[]"))
    except (TypeError, ValueError):
        current = set()

    await state.update_data(types=sorted(current))
    await callback.message.edit_text(
        f"Выбери вид(ы) тренировок (можно совместить не более {MAX_TRAINING_TYPES}):",
        reply_markup=kb.training_types_kb(current, prefix="ch_type"),
    )
    await state.set_state(ChangeTypes.waiting_types)
    await callback.answer()


@router.callback_query(ChangeTypes.waiting_types, F.data.startswith("ch_type_toggle:"))
async def ch_type_toggle(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":")[1]
    data = await state.get_data()
    selected = set(data.get("types", []))

    if key in selected:
        selected.discard(key)
    else:
        if len(selected) >= MAX_TRAINING_TYPES:
            await callback.answer(f"Можно выбрать не более {MAX_TRAINING_TYPES} видов", show_alert=True)
            return
        selected.add(key)

    await state.update_data(types=sorted(selected))
    await callback.message.edit_reply_markup(reply_markup=kb.training_types_kb(selected, prefix="ch_type"))
    await callback.answer()


@router.callback_query(ChangeTypes.waiting_types, F.data == "ch_type_done")
async def ch_type_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("types", [])

    if not selected:
        await callback.answer("Выбери хотя бы один вид", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id)
    await db.update_user(
        callback.from_user.id,
        training_types=json.dumps(selected),
        goal=selected[0],
    )

    place = user.get("training_place") or "home"
    training_days_raw = user.get("training_days")
    training_days = json.loads(training_days_raw) if training_days_raw else None

    plan = generate_weekly_plan(user["level"], place, selected, training_days=training_days, days_per_week=user.get("days_per_week"))
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    await db.save_weekly_plan(callback.from_user.id, week_start.isoformat(), plan)

    await state.clear()
    types_str = ", ".join(TRAINING_TYPES[k] for k in selected)
    await callback.message.edit_text(
        f"Вид тренировок обновлён: <b>{types_str}</b> ✅\nПлан на неделю пересобран под новые виды.",
        reply_markup=kb.back_to_menu_kb(),
    )
    await callback.answer()
