"""SQL-схема базы данных.

Все таблицы описаны одним скриптом. При старте бота
connection.py выполняет этот скрипт — создаёт таблицы, если их нет.
"""

CREATE_TABLES_SQL = """
-- Пользователи Telegram
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Машины пользователя
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER,
    engine TEXT,
    vin TEXT,
    mileage INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    photo_file_id TEXT,
    oil_interval_km INTEGER,
    license_plate TEXT,
    engine_volume TEXT,
    engine_power INTEGER,
    fuel_type TEXT,
    transmission TEXT,
    drivetrain TEXT,
    body_type TEXT,
    sts_number TEXT,
    pts_number TEXT,
    notes TEXT,                    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Все записи по машине (ТО, заправки, ремонт, замена деталей и т.д.)
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    date DATE NOT NULL,
    mileage INTEGER,
    cost REAL DEFAULT 0,
    description TEXT,
    data TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

-- Документы (СТС, ОСАГО, КАСКО и т.д.)
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    number TEXT,
    issued_at DATE,
    expires_at DATE,
    file_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

-- Напоминания (замена масла, страховка и т.д.)
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    trigger_date DATE,
    trigger_mileage INTEGER,
    sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_cars_user ON cars(user_id);
CREATE INDEX IF NOT EXISTS idx_records_car ON records(car_id);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_documents_car ON documents(car_id);
CREATE INDEX IF NOT EXISTS idx_reminders_car ON reminders(car_id);

-- Заметки о машине (отдельные записи)
CREATE TABLE IF NOT EXISTS car_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_car_notes_car ON car_notes(car_id);

-- История AI-диалога
CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_messages_car ON ai_messages(car_id);
"""
