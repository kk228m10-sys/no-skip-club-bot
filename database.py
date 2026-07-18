"""
Вся работа с SQLite базой. База создаётся автоматически в файле no_skip.db
рядом с ботом при первом запуске. Ничего дополнительно ставить не нужно.
"""

import json
from datetime import datetime, date

import aiosqlite

from config import DB_PATH

# Пороги стрика для стадий персонажа (мини-апп)
CHARACTER_STAGES = [
    (0, "Спящий", "Персонаж ещё спит. Первая тренировка его разбудит."),
    (1, "Пробуждение", "Первый шаг сделан. Держи темп."),
    (3, "Новобранец", "Тело начинает привыкать к нагрузке."),
    (7, "Боец", "Неделя без пропусков — уже видно результат."),
    (14, "Дисциплина", "Две недели подряд. Это уже характер, а не мотивация."),
    (28, "Несгибаемый", "Месяц без пропусков. Ты и есть No Skip Club."),
]


def get_character_stage(streak: int):
    stage = CHARACTER_STAGES[0]
    for threshold, name, desc in CHARACTER_STAGES:
        if streak >= threshold:
            stage = (threshold, name, desc)
    index = CHARACTER_STAGES.index(stage)
    return {
        "index": index,
        "threshold": stage[0],
        "name": stage[1],
        "description": stage[2],
        "next_threshold": CHARACTER_STAGES[index + 1][0] if index + 1 < len(CHARACTER_STAGES) else None,
    }


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                name TEXT,
                level TEXT,
                days_per_week INTEGER,
                training_days TEXT,
                goal TEXT,
                promise TEXT,
                streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                total_workouts INTEGER DEFAULT 0,
                last_training_date TEXT,
                onboarded INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        # Миграции для тех, кто уже запускал бота до появления новых полей —
        # просто добавляем колонки, если их ещё нет.
        for ddl in (
            "ALTER TABLE users ADD COLUMN training_days TEXT",
            "ALTER TABLE users ADD COLUMN training_place TEXT",
            "ALTER TABLE users ADD COLUMN training_types TEXT",
            "ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN blocked_at TEXT",
            "ALTER TABLE users ADD COLUMN weight REAL",
            "ALTER TABLE users ADD COLUMN gender TEXT",
        ):
            try:
                await db.execute(ddl)
                await db.commit()
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS weekly_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                week_start TEXT,
                plan_json TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workout_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                log_date TEXT,
                completed INTEGER,
                feeling TEXT,
                note TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                username TEXT,
                booking_date TEXT,
                slot TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT
            )
        """)
        # Миграция со старой свободной формы записи (name/preferred_time) на
        # фиксированные слоты (booking_date/slot).
        for ddl in (
            "ALTER TABLE bookings ADD COLUMN username TEXT",
            "ALTER TABLE bookings ADD COLUMN booking_date TEXT",
            "ALTER TABLE bookings ADD COLUMN slot TEXT",
        ):
            try:
                await db.execute(ddl)
                await db.commit()
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                place TEXT,
                level TEXT,
                media_type TEXT,
                file_id TEXT,
                caption TEXT,
                created_at TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_challenges (
                challenge_date TEXT PRIMARY KEY,
                gesture_key TEXT,
                emoji TEXT,
                name TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS proofs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                proof_date TEXT,
                gesture_key TEXT,
                file_id TEXT,
                verdict TEXT,
                created_at TEXT
            )
        """)
        await db.commit()


async def get_user(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def ensure_user(telegram_id: int, username: str):
    user = await get_user(telegram_id)
    if user:
        return user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (telegram_id, username, created_at, onboarded) VALUES (?, ?, ?, 0)",
            (telegram_id, username, datetime.utcnow().isoformat()),
        )
        await db.commit()
    return await get_user(telegram_id)


async def update_user(telegram_id: int, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [telegram_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {keys} WHERE telegram_id = ?", values)
        await db.commit()


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE onboarded = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def save_weekly_plan(telegram_id: int, week_start: str, plan: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO weekly_plans (telegram_id, week_start, plan_json) VALUES (?, ?, ?)",
            (telegram_id, week_start, json.dumps(plan, ensure_ascii=False)),
        )
        await db.commit()


async def get_current_weekly_plan(telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM weekly_plans WHERE telegram_id = ? ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        result = dict(row)
        result["plan"] = json.loads(result["plan_json"])
        return result


async def log_workout(telegram_id: int, completed: bool, feeling: str = None, note: str = None):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO workout_logs (telegram_id, log_date, completed, feeling, note) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, today, int(completed), feeling, note),
        )
        await db.commit()


async def has_logged_today(telegram_id: int):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM workout_logs WHERE telegram_id = ? AND log_date = ? AND completed = 1",
            (telegram_id, today),
        )
        row = await cur.fetchone()
        return row[0] > 0


async def get_workout_history(telegram_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM workout_logs WHERE telegram_id = ? ORDER BY id DESC LIMIT ?",
            (telegram_id, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def mark_workout_complete(telegram_id: int, feeling: str = None, note: str = None):
    """Отмечает тренировку выполненной, обновляет стрик и счётчики."""
    user = await get_user(telegram_id)
    today = date.today()
    today_iso = today.isoformat()

    already = await has_logged_today(telegram_id)
    if already:
        return user  # уже отмечено сегодня, ничего не меняем повторно

    await log_workout(telegram_id, True, feeling, note)

    new_streak = (user["streak"] or 0) + 1
    new_longest = max(new_streak, user["longest_streak"] or 0)
    new_total = (user["total_workouts"] or 0) + 1

    await update_user(
        telegram_id,
        streak=new_streak,
        longest_streak=new_longest,
        total_workouts=new_total,
        last_training_date=today_iso,
    )
    return await get_user(telegram_id)


async def reset_streak(telegram_id: int):
    await update_user(telegram_id, streak=0)


async def block_user(telegram_id: int):
    await update_user(telegram_id, blocked=1, blocked_at=datetime.utcnow().isoformat())


async def unblock_user(telegram_id: int):
    await update_user(telegram_id, blocked=0, blocked_at=None)


async def is_user_blocked(telegram_id: int) -> bool:
    user = await get_user(telegram_id)
    return bool(user and user.get("blocked"))


async def get_blocked_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE blocked = 1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def add_booking(telegram_id: int, username: str, booking_date: str, slot: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO bookings (telegram_id, username, booking_date, slot, created_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, username, booking_date, slot, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def count_bookings(booking_date: str, slot: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE booking_date = ? AND slot = ? AND status != 'cancelled'",
            (booking_date, slot),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_user_booking(telegram_id: int, booking_date: str, slot: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bookings WHERE telegram_id = ? AND booking_date = ? AND slot = ? AND status != 'cancelled'",
            (telegram_id, booking_date, slot),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_user_bookings(telegram_id: int):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bookings WHERE telegram_id = ? AND status != 'cancelled' AND booking_date >= ? "
            "ORDER BY booking_date, slot",
            (telegram_id, today),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def cancel_booking(booking_id: int, telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND telegram_id = ?",
            (booking_id, telegram_id),
        )
        await db.commit()


async def get_daily_challenge(challenge_date: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM daily_challenges WHERE challenge_date = ?", (challenge_date,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_daily_challenge(challenge_date: str, gesture_key: str, emoji: str, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO daily_challenges (challenge_date, gesture_key, emoji, name) "
            "VALUES (?, ?, ?, ?)",
            (challenge_date, gesture_key, emoji, name),
        )
        await db.commit()
    return await get_daily_challenge(challenge_date)


async def save_proof(telegram_id: int, proof_date: str, gesture_key: str, file_id: str, verdict: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO proofs (telegram_id, proof_date, gesture_key, file_id, verdict, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, proof_date, gesture_key, file_id, verdict, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def get_proof(proof_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM proofs WHERE id = ?", (proof_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def update_proof_verdict(proof_id: int, verdict: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE proofs SET verdict = ? WHERE id = ?",
            (verdict, proof_id),
        )
        await db.commit()


async def has_pending_proof_today(telegram_id: int) -> bool:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM proofs WHERE telegram_id = ? AND proof_date = ? AND verdict = 'pending'",
            (telegram_id, today),
        )
        row = await cur.fetchone()
        return row[0] > 0


async def get_pending_proofs(limit: int = 30):
    """Все заявки на подтверждение тренировки, ждущие решения админа."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM proofs WHERE verdict = 'pending' ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def add_material(place: str, level: str, media_type: str, file_id: str, caption: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO materials (place, level, media_type, file_id, caption, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (place, level, media_type, file_id, caption, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cur.lastrowid


async def get_materials(place: str, level: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM materials WHERE (place = ? OR place = 'all') AND (level = ? OR level = 'all') "
            "ORDER BY id DESC",
            (place, level),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
