"""FastAPI-бэкенд для Mini App."""
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI

from api.auth import validate_init_data
from services.db.connection import init_db, close_db
from services.db.queries import (
    get_or_create_user,
    get_active_car,
    get_records,
    get_fuel_stats,
    get_record_by_id,
    add_record,
    update_record,
    delete_record,
    get_monthly_expenses,
    get_next_oil_change,
    update_car_field,
    add_car_note,
    get_car_notes,
    get_car_note_by_id,
    update_car_note,
    delete_car_note,
    add_ai_message,
    get_ai_history,
    clear_ai_history,
    add_document,
    get_documents,
    delete_document,
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class NgrokSkipWarningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["ngrok-skip-browser-warning"] = "69420"
        return response

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Открывает базу при старте, закрывает при остановке."""
    await init_db()
    yield
    await close_db()


app = FastAPI(lifespan=lifespan)

app.add_middleware(NgrokSkipWarningMiddleware)


def get_telegram_user(init_data: str) -> dict:
    """Валидирует initData и возвращает telegram-пользователя."""
    if not init_data:
        raise HTTPException(status_code=401, detail="No initData")

    data = validate_init_data(init_data, BOT_TOKEN)
    if data is None:
        raise HTTPException(status_code=401, detail="Invalid initData")

    user_json = data.get("user")
    if not user_json:
        raise HTTPException(status_code=401, detail="No user in initData")

    return json.loads(user_json)


# ============ HTML ============


@app.get("/")
async def root():
    """Отдаём главный HTML Mini App."""
    return FileResponse(WEBAPP_DIR / "index.html")


# ============ МОДЕЛИ ============


class CarUpdate(BaseModel):
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    engine: str | None = None
    vin: str | None = None
    mileage: int | None = None
    license_plate: str | None = None
    oil_interval_km: int | None = None
    engine_volume: str | None = None
    engine_power: int | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    drivetrain: str | None = None
    body_type: str | None = None
    sts_number: str | None = None
    pts_number: str | None = None
    notes: str | None = None


class RecordCreate(BaseModel):
    type: str
    date: str
    mileage: int | None = None
    cost: float = 0
    description: str | None = None
    data: dict | None = None


class RecordUpdate(BaseModel):
    date: str | None = None
    mileage: int | None = None
    cost: float | None = None
    description: str | None = None
    data: dict | None = None


class NoteCreate(BaseModel):
    text: str


class NoteUpdate(BaseModel):
    text: str


class ChatRequest(BaseModel):
    message: str

class DocumentCreate(BaseModel):
    type: str
    number: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None


# ============ API: МАШИНА ============


@app.get("/api/car")
async def api_get_car(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Возвращает пользователя, активную машину, фото и счётчик до ТО."""
    tg_user = get_telegram_user(x_init_data)

    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])

    photo_url = None
    if car and car.get("photo_file_id"):
        try:
            from aiogram import Bot
            bot = Bot(token=BOT_TOKEN)
            file = await bot.get_file(car["photo_file_id"])
            photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
            await bot.session.close()
        except Exception:
            photo_url = None

    next_oil_change = None
    if car:
        next_oil_change = await get_next_oil_change(car["id"])

    return {
        "user": user,
        "car": car,
        "photo_url": photo_url,
        "next_oil_change": next_oil_change,
    }


@app.patch("/api/car")
async def api_update_car(
    payload: CarUpdate,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Обновляет поля активной машины."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    field_map = {
        "brand": payload.brand,
        "model": payload.model,
        "year": payload.year,
        "engine": payload.engine,
        "vin": payload.vin,
        "mileage": payload.mileage,
        "license_plate": payload.license_plate,
        "oil_interval_km": payload.oil_interval_km,
        "engine_volume": payload.engine_volume,
        "engine_power": payload.engine_power,
        "fuel_type": payload.fuel_type,
        "transmission": payload.transmission,
        "drivetrain": payload.drivetrain,
        "body_type": payload.body_type,
        "sts_number": payload.sts_number,
        "pts_number": payload.pts_number,
        "notes": payload.notes,
    }

    for field, value in field_map.items():
        if value is not None:
            await update_car_field(car["id"], field, value)

    return {"ok": True}


# ============ API: СТАТИСТИКА ============


@app.get("/api/stats/fuel")
async def api_fuel_stats(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Статистика по топливу за текущий месяц."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"total_cost": 0, "total_liters": 0, "avg_consumption": None}

    today = datetime.now()
    stats = await get_fuel_stats(car["id"], today.year, today.month)
    return stats


@app.get("/api/stats/monthly")
async def api_monthly_stats(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Расходы по месяцам — для графика на главной."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"months": []}

    months = await get_monthly_expenses(car["id"], months=6)
    return {"months": months}


# ============ API: ЗАПИСИ ============


@app.get("/api/records")
async def api_records(
    limit: int = 5,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Последние записи по активной машине."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"records": []}

    records = await get_records(car["id"], limit=limit)
    return {"records": records}


@app.get("/api/records-list")
async def api_records_all(
    type: str | None = None,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Все записи по активной машине. Опциональный фильтр по типу."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"records": []}

    records = await get_records(car["id"], record_type=type, limit=500)
    return {"records": records}


@app.post("/api/records")
async def api_create_record(
    payload: RecordCreate,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Создаёт новую запись по активной машине."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    record_id = await add_record(
        car_id=car["id"],
        record_type=payload.type,
        date=payload.date,
        mileage=payload.mileage,
        cost=payload.cost,
        description=payload.description,
        data=payload.data,
    )
    return {"id": record_id, "ok": True}


@app.patch("/api/records/{record_id}")
async def api_update_record(
    record_id: int,
    payload: RecordUpdate,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Обновляет запись. Проверяет, что она принадлежит пользователю."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    record = await get_record_by_id(record_id)
    if not record or record["car_id"] != car["id"]:
        raise HTTPException(status_code=404, detail="Record not found")

    ok = await update_record(
        record_id=record_id,
        date=payload.date,
        mileage=payload.mileage,
        cost=payload.cost,
        description=payload.description,
        data=payload.data,
    )
    return {"ok": ok}


@app.delete("/api/records/{record_id}")
async def api_delete_record(
    record_id: int,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Удаляет запись. Проверяет, что она принадлежит пользователю."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    record = await get_record_by_id(record_id)
    if not record or record["car_id"] != car["id"]:
        raise HTTPException(status_code=404, detail="Record not found")

    ok = await delete_record(record_id)
    return {"ok": ok}


# ============ API: ЗАМЕТКИ ============


@app.get("/api/car/notes")
async def api_get_notes(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Все заметки по активной машине."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"notes": []}

    notes = await get_car_notes(car["id"])
    return {"notes": notes}


@app.post("/api/car/notes")
async def api_create_note(
    payload: NoteCreate,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Создаёт новую заметку."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty note")

    note_id = await add_car_note(car["id"], text)
    return {"id": note_id, "ok": True}


@app.patch("/api/car/notes/{note_id}")
async def api_update_note(
    note_id: int,
    payload: NoteUpdate,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Обновляет заметку."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    note = await get_car_note_by_id(note_id)
    if not note or note["car_id"] != car["id"]:
        raise HTTPException(status_code=404, detail="Note not found")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty note")

    ok = await update_car_note(note_id, text)
    return {"ok": ok}


@app.delete("/api/car/notes/{note_id}")
async def api_delete_note(
    note_id: int,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Удаляет заметку."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    note = await get_car_note_by_id(note_id)
    if not note or note["car_id"] != car["id"]:
        raise HTTPException(status_code=404, detail="Note not found")

    ok = await delete_car_note(note_id)
    return {"ok": ok}


# ============ API: AI-ПОМОЩНИК ============


@app.get("/api/ai/history")
async def api_ai_history(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """История AI-диалога для активной машины."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"messages": []}

    messages = await get_ai_history(car["id"], limit=50)
    return {"messages": messages}


@app.delete("/api/ai/history")
async def api_clear_ai_history(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Очищает историю AI-диалога."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"ok": False}

    await clear_ai_history(car["id"])
    return {"ok": True}


@app.post("/api/ai/chat")
async def api_ai_chat(
    payload: ChatRequest,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """AI-помощник. Собирает контекст о машине, шлёт в DeepSeek, возвращает ответ."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    # Сохраняем вопрос пользователя
    await add_ai_message(car["id"], "user", payload.message)

    # Собираем контекст
    notes = await get_car_notes(car["id"])
    records = await get_records(car["id"], limit=50)
    monthly = await get_monthly_expenses(car["id"], months=6)
    fuel_stats = await get_fuel_stats(car["id"], datetime.now().year, datetime.now().month)

    # Блок «автомобиль»
    car_lines = [f"{car['brand']} {car['model']}"]
    if car.get("year"):
        car_lines.append(f"Год: {car['year']}")
    if car.get("license_plate"):
        car_lines.append(f"Госномер: {car['license_plate']}")
    if car.get("vin"):
        car_lines.append(f"VIN: {car['vin']}")
    if car.get("mileage"):
        car_lines.append(f"Пробег: {car['mileage']} км")
    if car.get("engine_volume"):
        eng = f"Двигатель: {car['engine_volume']} л"
        if car.get("engine_power"):
            eng += f", {car['engine_power']} л.с."
        if car.get("fuel_type"):
            eng += f", {car['fuel_type']}"
        car_lines.append(eng)
    if car.get("transmission"):
        car_lines.append(f"Трансмиссия: {car['transmission']}")
    if car.get("drivetrain"):
        car_lines.append(f"Привод: {car['drivetrain']}")
    if car.get("body_type"):
        car_lines.append(f"Кузов: {car['body_type']}")
    if car.get("oil_interval_km"):
        car_lines.append(f"Интервал замены масла: {car['oil_interval_km']} км")

    notes_text = "\n".join(f"- {n['text']}" for n in notes) if notes else "(нет заметок)"

    records_lines = []
    for r in records[:15]:
        desc = r.get("description") or r.get("type")
        records_lines.append(f"- {r['date']}: {desc} (пробег: {r.get('mileage') or '—'} км)")
    records_text = "\n".join(records_lines) if records_lines else "(нет записей)"

    monthly_text = "\n".join(f"- {m['label']} {m['year']}: {m['total']} руб." for m in monthly)

    # ============ ПРОМПТ ТАЛОСА ============
    system_prompt = (
        "Ты — Талос, AI-помощник по уходу за автомобилем. "
        "Ты опытный автомеханик с 20-летним стажем. Твой характер — как у бронзового стража: "
        "надежный, точный, спокойный и невозмутимый. Общайся на «ты», уверенно, дружелюбно, без лишних эмоций. "
        "Пиши только простой текст, без Markdown."
    )

    user_content = (
        f"Данные об автомобиле:\n{chr(10).join(car_lines)}\n\n"
        f"Заметки пользователя:\n{notes_text}\n\n"
        f"Последние записи (ТО, заправки, ремонты):\n{records_text}\n\n"
        f"Расходы по месяцам:\n{monthly_text}\n\n"
        f"Топливо в этом месяце: {fuel_stats['total_cost']} руб. ({fuel_stats['total_liters']} л)\n\n"
        f"Вопрос пользователя: {payload.message}\n\n"
        "ПРАВИЛА ОТВЕТА:\n"
        "1. Отвечай кратко (2-5 предложений). Сначала прямой ответ, затем детали.\n"
        "2. Для вопросов о пробегах, датах, расходах и обслуживании конкретной машины используй только данные из дневника. Если их нет — скажи: «В твоем дневнике этой информации нет».\n"
        "3. Если вопрос касается общих технических знаний (артикулы, устройство, типичные болезни модели), и этого нет в дневнике — используй свои знания. Обязательно начни ответ с фразы: «В твоем дневнике этой информации нет, но в целом...»\n"
        "4. Не выдумывай конкретные пробеги, даты и суммы, которых нет в базе.\n"
        "5. Если видишь противоречие в данных (например, пробег в записи больше текущего) — укажи на это.\n"
        "6. Не давай юридических советов, не рекламируй конкретные СТО или магазины.\n"
        "7. Не используй капс и формальные обращения. Пиши как живой человек.\n"
    )

    # Получаем последние 10 сообщений из истории
    history = await get_ai_history(car["id"], limit=10)
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Добавляем историю в запрос (пропускаем последнее, так как это текущий вопрос)
    for msg in history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
        
    # Добавляем текущий вопрос с контекстом
    messages.append({"role": "user", "content": user_content})

    try:
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=1000,
            temperature=0.3,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error: {str(e)}")

    # Сохраняем ответ AI
    await add_ai_message(car["id"], "assistant", answer)

    return {"answer": answer}

# ============ API: ДОКУМЕНТЫ ============

@app.get("/api/documents")
async def api_get_documents(
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Все документы по активной машине."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        return {"documents": []}

    docs = await get_documents(car["id"])
    return {"documents": docs}


@app.post("/api/documents")
async def api_create_document(
    payload: DocumentCreate,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Создаёт документ."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    doc_id = await add_document(
        car_id=car["id"],
        doc_type=payload.type,
        number=payload.number,
        issued_at=payload.issued_at,
        expires_at=payload.expires_at,
    )
    return {"id": doc_id, "ok": True}


@app.delete("/api/documents/{doc_id}")
async def api_delete_document(
    doc_id: int,
    x_init_data: str = Header(..., alias="X-Init-Data"),
):
    """Удаляет документ."""
    tg_user = get_telegram_user(x_init_data)
    user = await get_or_create_user(
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
    car = await get_active_car(user["id"])
    if not car:
        raise HTTPException(status_code=404, detail="No active car")

    ok = await delete_document(doc_id)
    return {"ok": ok}