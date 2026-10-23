"""Подключение к базе данных SQLite.

Используем aiosqlite — асинхронный драйвер.
Почему асинхронный: бот на aiogram работает в event loop,
и обычный синхронный sqlite3 заблокировал бы весь бот на время запроса.
"""

import aiosqlite
from pathlib import Path

# Путь к файлу базы: <корень проекта>/data/mycar.db
DB_PATH = Path(__file__).parent.parent.parent / "data" / "mycar.db"

# Глобальное подключение. Инициализируется один раз при старте бота.
_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    """Открывает подключение и создаёт таблицы, если их нет.

    Вызывается один раз при запуске бота или бэкенда.
    """
    global _db

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row

    from services.db.models import CREATE_TABLES_SQL

    await _db.executescript(CREATE_TABLES_SQL)
    await _db.commit()

    # Миграции — добавляем поля в существующие таблицы
    await _migrate(_db)


async def _migrate(db: aiosqlite.Connection) -> None:
    """Добавляет недостающие поля в существующие таблицы."""
    async with db.execute("PRAGMA table_info(cars)") as cursor:
        cols = await cursor.fetchall()
        col_names = [c["name"] for c in cols]

    if "photo_file_id" not in col_names:
        await db.execute("ALTER TABLE cars ADD COLUMN photo_file_id TEXT")
        await db.commit()

    if "oil_interval_km" not in col_names:
        await db.execute("ALTER TABLE cars ADD COLUMN oil_interval_km INTEGER")
        await db.commit()

    if "license_plate" not in col_names:
        await db.execute("ALTER TABLE cars ADD COLUMN license_plate TEXT")
        await db.commit()

    # Новые технические поля
    new_fields = {
        "engine_volume": "TEXT",
        "engine_power": "INTEGER",
        "fuel_type": "TEXT",
        "transmission": "TEXT",
        "drivetrain": "TEXT",
        "body_type": "TEXT",
        "sts_number": "TEXT",
        "pts_number": "TEXT",
    }
    for field_name, field_type in new_fields.items():
        if field_name not in col_names:
            await db.execute(f"ALTER TABLE cars ADD COLUMN {field_name} {field_type}")
    await db.commit()

    # Поле notes в таблице cars
    if "notes" not in col_names:
        await db.execute("ALTER TABLE cars ADD COLUMN notes TEXT")
        await db.commit()

    # Таблица car_notes создаётся через CREATE_TABLES_SQL,
    # но на случай если база старая — создаём отдельно
    await db.execute("""
        CREATE TABLE IF NOT EXISTS car_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        )
    """)
    await db.commit()

        # Таблица ai_messages
    await db.execute("""
        CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        )
    """)
    await db.commit()

async def get_db() -> aiosqlite.Connection:
    """Возвращает активное подключение."""
    if _db is None:
        raise RuntimeError("База не инициализирована. Вызови init_db() сначала.")
    return _db


async def close_db() -> None:
    """Закрывает подключение. Вызывается при остановке бота."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
