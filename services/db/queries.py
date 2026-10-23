"""Функции для работы с базой данных.

Каждая функция делает одну вещь. Хендлеры бота и API вызывают их,
а не пишут SQL напрямую.
"""
import json
from datetime import datetime, timedelta
from typing import Any

from services.db.connection import get_db


# ============ USERS ============

async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> dict[str, Any]:
    """Возвращает пользователя по telegram_id. Создаёт, если его нет."""
    db = await get_db()

    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row:
            return dict(row)

    await db.execute(
        "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
        (telegram_id, username, first_name),
    )
    await db.commit()

    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row)


# ============ CARS ============
async def add_car(
    user_id: int,
    brand: str,
    model: str,
    year: int | None = None,
    engine: str | None = None,
    vin: str | None = None,
    mileage: int = 0,
    license_plate: str | None = None,
) -> int:
    """Добавляет машину. Возвращает её id.

    Если у пользователя ещё нет машин — новая становится активной.
    """
    db = await get_db()

    async with db.execute(
        "SELECT COUNT(*) as cnt FROM cars WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        is_active = 1 if row["cnt"] == 0 else 0

    cursor = await db.execute(
        """INSERT INTO cars (user_id, brand, model, year, engine, vin, mileage, is_active, license_plate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, brand, model, year, engine, vin, mileage, is_active, license_plate),
    )
    await db.commit()
    return cursor.lastrowid


async def get_user_cars(user_id: int) -> list[dict[str, Any]]:
    """Все машины пользователя. Активная — первой."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM cars WHERE user_id = ? ORDER BY is_active DESC, created_at ASC",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_active_car(user_id: int) -> dict[str, Any] | None:
    """Активная машина пользователя. None, если машин нет."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM cars WHERE user_id = ? AND is_active = 1 LIMIT 1",
        (user_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_active_car(user_id: int, car_id: int) -> None:
    """Делает машину активной. Остальные машины пользователя — неактивные."""
    db = await get_db()
    await db.execute(
        "UPDATE cars SET is_active = 0 WHERE user_id = ?", (user_id,)
    )
    await db.execute(
        "UPDATE cars SET is_active = 1 WHERE id = ? AND user_id = ?",
        (car_id, user_id),
    )
    await db.commit()


async def update_car_photo(car_id: int, file_id: str | None) -> None:
    """Сохраняет file_id фото машины. Передай None, чтобы удалить фото."""
    db = await get_db()
    await db.execute(
        "UPDATE cars SET photo_file_id = ? WHERE id = ?",
        (file_id, car_id),
    )
    await db.commit()


async def update_car_field(car_id: int, field: str, value) -> None:
    """Обновляет одно поле машины. Работает только с разрешёнными полями."""
    allowed = {
        "brand", "model", "year", "engine", "vin",
        "mileage", "oil_interval_km", "license_plate",
        "engine_volume", "engine_power", "fuel_type",
        "transmission", "drivetrain", "body_type",
        "sts_number", "pts_number", "notes",
    }
    if field not in allowed:
        raise ValueError(f"Недопустимое поле: {field}")

    db = await get_db()
    await db.execute(
        f"UPDATE cars SET {field} = ? WHERE id = ?",
        (value, car_id),
    )
    await db.commit()


# ============ RECORDS ============

async def add_record(
    car_id: int,
    record_type: str,
    date: str,
    mileage: int | None = None,
    cost: float = 0,
    description: str | None = None,
    data: dict | None = None,
) -> int:
    """Добавляет запись по машине. Возвращает id записи.

    record_type: fuel / maintenance / repair / part / expense / note
    date: в формате 'YYYY-MM-DD'
    data: словарь с доп. полями, будет сохранён как JSON.
    """
    db = await get_db()
    data_json = json.dumps(data or {}, ensure_ascii=False)

    cursor = await db.execute(
        """INSERT INTO records (car_id, type, date, mileage, cost, description, data)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (car_id, record_type, date, mileage, cost, description, data_json),
    )
    await db.commit()

    # Если у записи пробег больше текущего у машины — обновляем пробег машины
    if mileage and mileage > 0:
        async with db.execute(
            "SELECT mileage FROM cars WHERE id = ?", (car_id,)
        ) as cursor2:
            car_row = await cursor2.fetchone()
        if car_row and (car_row["mileage"] or 0) < mileage:
            await db.execute(
                "UPDATE cars SET mileage = ? WHERE id = ?",
                (mileage, car_id),
            )
            await db.commit()

    return cursor.lastrowid


async def get_records(
    car_id: int,
    record_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Записи по машине, свежие — первыми.

    Если record_type задан — только этого типа.
    """
    db = await get_db()

    if record_type:
        sql = """SELECT * FROM records WHERE car_id = ? AND type = ?
                 ORDER BY date DESC, id DESC LIMIT ?"""
        params = (car_id, record_type, limit)
    else:
        sql = """SELECT * FROM records WHERE car_id = ?
                 ORDER BY date DESC, id DESC LIMIT ?"""
        params = (car_id, limit)

    async with db.execute(sql, params) as cursor:
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d["data"]) if d["data"] else {}
            result.append(d)
        return result


async def get_record_by_id(record_id: int) -> dict | None:
    """Возвращает одну запись по id. None, если не найдена."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM records WHERE id = ?", (record_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = json.loads(d["data"]) if d["data"] else {}
        return d


async def delete_record(record_id: int) -> bool:
    """Удаляет запись. Возвращает True, если что-то удалили."""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM records WHERE id = ?", (record_id,)
    )
    await db.commit()
    return cursor.rowcount > 0


async def update_record(
    record_id: int,
    date: str | None = None,
    mileage: int | None = None,
    cost: float | None = None,
    description: str | None = None,
    data: dict | None = None,
) -> bool:
    """Обновляет поля записи. Передавай только то, что нужно изменить."""
    db = await get_db()

    fields = []
    values = []

    if date is not None:
        fields.append("date = ?")
        values.append(date)
    if mileage is not None:
        fields.append("mileage = ?")
        values.append(mileage)
    if cost is not None:
        fields.append("cost = ?")
        values.append(cost)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if data is not None:
        fields.append("data = ?")
        values.append(json.dumps(data, ensure_ascii=False))

    if not fields:
        return False

    values.append(record_id)
    sql = f"UPDATE records SET {', '.join(fields)} WHERE id = ?"
    cursor = await db.execute(sql, values)
    await db.commit()
    return cursor.rowcount > 0


# ============ СТАТИСТИКА ============

async def get_fuel_stats(car_id: int, year: int, month: int) -> dict[str, Any]:
    """Статистика по топливу за месяц.

    Возвращает сумму расходов, литров и средний расход л/100 км.
    Средний расход считается по пробегу между первой и последней заправкой.
    """
    db = await get_db()

    month_mask = f"{year:04d}-{month:02d}%"

    async with db.execute(
        """SELECT cost, mileage, data FROM records
           WHERE car_id = ? AND type = 'fuel' AND date LIKE ?
           ORDER BY date ASC, id ASC""",
        (car_id, month_mask),
    ) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        return {"total_cost": 0, "total_liters": 0, "avg_consumption": None}

    total_cost = 0.0
    total_liters = 0.0
    for r in rows:
        total_cost += r["cost"] or 0
        data = json.loads(r["data"]) if r["data"] else {}
        total_liters += data.get("liters", 0)

    # Средний расход: между первой и последней заправкой с пробегом
    with_mileage = [r for r in rows if r["mileage"] and r["mileage"] > 0]
    avg = None
    if len(with_mileage) >= 2:
        first = with_mileage[0]
        last = with_mileage[-1]
        distance = last["mileage"] - first["mileage"]
        if distance > 0 and total_liters > 0:
            avg = round(total_liters / distance * 100, 1)

    return {
        "total_cost": round(total_cost, 2),
        "total_liters": round(total_liters, 2),
        "avg_consumption": avg,
    }


async def get_monthly_expenses(car_id: int, months: int = 6) -> list[dict]:
    """Возвращает сумму расходов по месяцам за последние N месяцев."""
    db = await get_db()
    today = datetime.now()

    result = []
    for i in range(months - 1, -1, -1):
        first = today.replace(day=1)
        for _ in range(i):
            first = (first - timedelta(days=1)).replace(day=1)

        year = first.year
        month = first.month
        mask = f"{year:04d}-{month:02d}%"

        async with db.execute(
            "SELECT COALESCE(SUM(cost), 0) as total FROM records "
            "WHERE car_id = ? AND date LIKE ?",
            (car_id, mask),
        ) as cursor:
            row = await cursor.fetchone()

        month_names = ["янв", "фев", "мар", "апр", "май", "июн",
                       "июл", "авг", "сен", "окт", "ноя", "дек"]
        result.append({
            "year": year,
            "month": month,
            "total": float(row["total"] or 0),
            "label": month_names[month - 1],
        })

    return result


# ============ СЧЁТЧИК ДО ТО ============

async def get_next_oil_change(car_id: int) -> dict | None:
    """Возвращает расчёт до следующей замены масла.

    Логика:
    1. Берём интервал из cars.oil_interval_km.
    2. Ищем последнюю запись ТО с data.work == 'oil_change', у которой ЕСТЬ пробег.
    3. Считаем: next = last_mileage + interval.
    4. km_left = next - current_mileage.

    Записи без пробега пропускаются, чтобы счётчик работал,
    даже если пользователь заполняет пробег не всегда.

    Возвращает None, если интервал не задан или нет ни одной замены масла с пробегом.
    """
    db = await get_db()

    async with db.execute(
        "SELECT mileage, oil_interval_km FROM cars WHERE id = ?", (car_id,)
    ) as cursor:
        car = await cursor.fetchone()

    if not car or not car["oil_interval_km"]:
        return None

    interval = car["oil_interval_km"]
    current_mileage = car["mileage"] or 0

    # Ищем последнюю запись о замене масла С ПРОБЕГОМ
    async with db.execute(
        """SELECT mileage, date FROM records
           WHERE car_id = ?
             AND type = 'maintenance'
             AND data LIKE '%oil_change%'
             AND mileage IS NOT NULL
             AND mileage > 0
           ORDER BY date DESC, id DESC LIMIT 1""",
        (car_id,),
    ) as cursor:
        last = await cursor.fetchone()

    if not last or not last["mileage"]:
        return None

    last_mileage = last["mileage"]
    next_mileage = last_mileage + interval
    km_left = next_mileage - current_mileage

    return {
        "last_mileage": last_mileage,
        "last_date": last["date"],
        "interval": interval,
        "next_mileage": next_mileage,
        "current_mileage": current_mileage,
        "km_left": km_left,
    }

# ============ ЗАМЕТКИ О МАШИНЕ ============

async def add_car_note(car_id: int, text: str) -> int:
    """Добавляет новую заметку. Возвращает id."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO car_notes (car_id, text) VALUES (?, ?)",
        (car_id, text),
    )
    await db.commit()
    return cursor.lastrowid


async def get_car_notes(car_id: int) -> list[dict]:
    """Все заметки по машине. Свежие — первыми."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM car_notes WHERE car_id = ? ORDER BY created_at DESC, id DESC",
        (car_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_car_note_by_id(note_id: int) -> dict | None:
    """Одна заметка по id."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM car_notes WHERE id = ?", (note_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_car_note(note_id: int, text: str) -> bool:
    """Обновляет текст заметки."""
    db = await get_db()
    cursor = await db.execute(
        "UPDATE car_notes SET text = ? WHERE id = ?",
        (text, note_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_car_note(note_id: int) -> bool:
    """Удаляет заметку."""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM car_notes WHERE id = ?", (note_id,)
    )
    await db.commit()
    return cursor.rowcount > 0

# ============ AI-ИСТОРИЯ ============

async def add_ai_message(car_id: int, role: str, content: str) -> int:
    """Сохраняет сообщение в историю AI. role = 'user' или 'assistant'."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO ai_messages (car_id, role, content) VALUES (?, ?, ?)",
        (car_id, role, content),
    )
    await db.commit()
    return cursor.lastrowid


async def get_ai_history(car_id: int, limit: int = 50) -> list[dict]:
    """История AI-диалога. Свежие — последними."""
    db = await get_db()
    async with db.execute(
        """SELECT * FROM ai_messages
           WHERE car_id = ?
           ORDER BY id DESC LIMIT ?""",
        (car_id, limit),
    ) as cursor:
        rows = await cursor.fetchall()
        # Возвращаем в хронологическом порядке (старые → новые)
        return [dict(r) for r in reversed(rows)]


async def clear_ai_history(car_id: int) -> None:
    """Очищает историю AI-диалога."""
    db = await get_db()
    await db.execute("DELETE FROM ai_messages WHERE car_id = ?", (car_id,))
    await db.commit()

# ============ ДОКУМЕНТЫ ============

async def add_document(
    car_id: int,
    doc_type: str,
    number: str | None = None,
    issued_at: str | None = None,
    expires_at: str | None = None,
) -> int:
    """Добавляет документ по машине."""
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO documents (car_id, type, number, issued_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (car_id, doc_type, number, issued_at, expires_at),
    )
    await db.commit()
    return cursor.lastrowid


async def get_documents(car_id: int) -> list[dict]:
    """Все документы по машине."""
    db = await get_db()
    async with db.execute(
        "SELECT * FROM documents WHERE car_id = ? ORDER BY expires_at ASC, id DESC",
        (car_id,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_document(doc_id: int) -> bool:
    """Удаляет документ."""
    db = await get_db()
    cursor = await db.execute(
        "DELETE FROM documents WHERE id = ?", (doc_id,)
    )
    await db.commit()
    return cursor.rowcount > 0