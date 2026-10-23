"""Обработчики для раздела «Моё авто»."""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from bot.states import AddCar, EditCar, SetOilInterval
from bot.keyboards.main_menu import get_main_menu
from services.db.queries import (
    get_or_create_user,
    get_active_car,
    add_car,
    update_car_photo,
    update_car_field,
)

import re

def normalize_license_plate(raw: str) -> str:
    """Приводит госномер к формату 'А111АА 198'.

    - Убирает всё, кроме букв, цифр, пробелов
    - Буквы → заглавные
    - Вставляет пробел перед регионом (последние 2-3 цифры)
    """
    # Только буквы, цифры, пробелы
    cleaned = re.sub(r'[^A-Za-zА-Яа-я0-9\s]', '', raw).upper()
    # Убираем все пробелы — будем расставлять заново
    cleaned = re.sub(r'\s+', '', cleaned)

    # Стандартный формат: 1 буква + 3 цифры + 2 буквы + регион (2-3 цифры)
    # Пример: А111АА198 → А111АА 198
    # Пример: A198PN778 → A198PN 778

    # Ищем регион в конце — 2 или 3 цифры
    match = re.match(r'^([A-ZА-Я]\d{3}[A-ZА-Я]{2})(\d{2,3})$', cleaned)
    if match:
        return f"{match.group(1)} {match.group(2)}"

    # Если не подошло — возвращаем как есть капсом
    return cleaned

router = Router()


# ============ КНОПКА «МОЁ АВТО» ============
@router.message(F.text == "🚗 Моё авто")
async def show_car(message: Message, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car = await get_active_car(user["id"])

    if car is None:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="➕ Добавить машину")]],
            resize_keyboard=True,
        )
        await message.answer(
            "У тебя пока нет добавленной машины.\n\nХочешь добавить?",
            reply_markup=keyboard,
        )
        return

    interval = car["oil_interval_km"]
    interval_text = f"{interval:,} км".replace(",", " ") if interval else "не задан"
    plate_text = car["license_plate"] or "—"

    text = (
        f"🚗 <b>{car['brand']} {car['model']}</b>\n"
        f"Год: {car['year'] or '—'}\n"
        f"Двигатель: {car['engine'] or '—'}\n"
        f"Госномер: <b>{plate_text}</b>\n"
        f"VIN: {car['vin'] or '—'}\n"
        f"Пробег: {car['mileage']:,} км\n\n"
        f"⚙️ Интервал замены масла: <b>{interval_text}</b>"
    )

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📸 Загрузить фото")],
            [KeyboardButton(text="⚙️ Настроить ТО")],
            [KeyboardButton(text="✏️ Редактировать")],
            [KeyboardButton(text="↩️ В меню")],
        ],
        resize_keyboard=True,
    )
    await message.answer(text, reply_markup=keyboard)

# ============ ДОБАВЛЕНИЕ МАШИНЫ ============
@router.message(F.text == "➕ Добавить машину")
async def start_add_car(message: Message, state: FSMContext):
    await state.set_state(AddCar.brand)
    await message.answer(
        "Введи <b>марку</b> машины (например, Toyota).\n\n"
        "Чтобы отменить — отправь /cancel.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(AddCar.brand)
async def process_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text.strip())
    await state.set_state(AddCar.model)
    await message.answer("Теперь введи <b>модель</b> (например, Camry).")


@router.message(AddCar.model)
async def process_model(message: Message, state: FSMContext):
    await state.update_data(model=message.text.strip())
    await state.set_state(AddCar.year)
    await message.answer("Введи <b>год выпуска</b> (например, 2020).")


@router.message(AddCar.year)
async def process_year(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or not (1900 <= int(text) <= 2100):
        await message.answer("Пожалуйста, введи год числом от 1900 до 2100.")
        return
    await state.update_data(year=int(text))
    await state.set_state(AddCar.mileage)
    await message.answer("Введи текущий <b>пробег</b> в км (например, 78420).")


@router.message(AddCar.mileage)
async def process_mileage(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "").replace(",", "")
    if not text.isdigit():
        await message.answer("Пожалуйста, введи пробег числом (без букв).")
        return
    await state.update_data(mileage=int(text))

    # Спрашиваем госномер (опционально)
    await state.set_state(AddCar.license_plate)
    await message.answer(
        "Введи <b>госномер</b> машины (например, <code>А111АА 198</code>).\n\n"
        "Формат: 1 буква + 3 цифры + 2 буквы + пробел + регион.\n"
        "Буквы — заглавные.\n\n"
        "Если не хочешь указывать — отправь <code>—</code> (тире)."
    )


@router.message(AddCar.license_plate)
async def process_license_plate(message: Message, state: FSMContext):
    """Принимает госномер или пропускает."""
    raw = message.text.strip()

    # Если отправили «—» или «-» — пропускаем
    if raw in ("—", "-", "–", "пропустить", "нет"):
        license_plate = None
    else:
        license_plate = normalize_license_plate(raw)
    await state.update_data(license_plate=license_plate)

    # Показываем итог
    data = await state.get_data()
    plate_text = data.get("license_plate") or "не указан"

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Сохранить")],
            [KeyboardButton(text="❌ Отменить")],
        ],
        resize_keyboard=True,
    )
    await state.set_state(AddCar.confirm)
    await message.answer(
        "Проверь данные:\n\n"
        f"🚗 <b>{data['brand']} {data['model']}</b>\n"
        f"Год: {data['year']}\n"
        f"Пробег: {data['mileage']:,} км\n"
        f"Госномер: {plate_text}\n\n"
        "Всё верно?",
        reply_markup=keyboard,
    )


@router.message(AddCar.confirm, F.text == "✅ Сохранить")
async def save_car(message: Message, state: FSMContext):
    data = await state.get_data()
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car_id = await add_car(
        user_id=user["id"],
        brand=data["brand"],
        model=data["model"],
        year=data["year"],
        mileage=data["mileage"],
        license_plate=data.get("license_plate"),
    )
    await state.clear()
    await message.answer(
        f"✅ Машина сохранена (id={car_id}).\n\n"
        "Теперь можешь вести дневник ухода.",
        reply_markup=get_main_menu(),
    )


@router.message(AddCar.confirm, F.text == "❌ Отменить")
async def cancel_save(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ок, отменил.", reply_markup=get_main_menu())


# ============ ФОТО МАШИНЫ ============


@router.message(F.text == "📸 Загрузить фото")
async def ask_photo(message: Message, state: FSMContext):
    await state.update_data(waiting_photo=True)
    await message.answer(
        "Пришли фото машины.\n\nЧтобы отменить — /cancel.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("waiting_photo"):
        return

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car = await get_active_car(user["id"])
    if car is None:
        return

    file_id = message.photo[-1].file_id
    await update_car_photo(car["id"], file_id)
    await state.update_data(waiting_photo=False)

    await message.answer(
        "✅ Фото сохранено. Открой приложение, чтобы увидеть.",
        reply_markup=get_main_menu(),
    )


# ============ РЕДАКТИРОВАНИЕ МАШИНЫ ============


@router.message(F.text == "✏️ Редактировать")
async def edit_car_menu(message: Message, state: FSMContext):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car = await get_active_car(user["id"])
    if car is None:
        await message.answer("Сначала добавь машину.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Марка", callback_data="edit:brand"),
             InlineKeyboardButton(text="Модель", callback_data="edit:model")],
            [InlineKeyboardButton(text="Год", callback_data="edit:year"),
             InlineKeyboardButton(text="Двигатель", callback_data="edit:engine")],
            [InlineKeyboardButton(text="Госномер", callback_data="edit:license_plate"),
             InlineKeyboardButton(text="VIN", callback_data="edit:vin")],
            [InlineKeyboardButton(text="Пробег", callback_data="edit:mileage")],
        ]
    )
    await message.answer(
        f"Что хочешь изменить?\n\n"
        f"🚗 <b>{car['brand']} {car['model']}</b>\n"
        f"Год: {car['year'] or '—'} · Двигатель: {car['engine'] or '—'}\n"
        f"Госномер: {car['license_plate'] or '—'}\n"
        f"VIN: {car['vin'] or '—'} · Пробег: {car['mileage']:,} км",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("edit:"))
async def edit_car_choose_field(callback: CallbackQuery, state: FSMContext):
    """Пользователь выбрал поле — просим новое значение."""
    field = callback.data.split(":", 1)[1]

    # Расшифровка поля для человеческого текста
    field_labels = {
        "brand": "марку",
        "model": "модель",
        "year": "год выпуска",
        "engine": "двигатель",
        "vin": "VIN",
        "mileage": "пробег в км",
        "license_plate": "госномер (например, А111АА 198)",
    }

    await state.update_data(edit_field=field)
    await state.set_state(EditCar.new_value)

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Введи новое значение — {field_labels[field]}.\n\nЧтобы отменить — /cancel.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.answer()


@router.message(EditCar.new_value)
async def edit_car_save_value(message: Message, state: FSMContext):
    """Получили новое значение — валидируем и сохраняем."""
    data = await state.get_data()
    field = data.get("edit_field")
    if not field:
        await state.clear()
        await message.answer(
            "Что-то пошло не так. Возвращаемся в меню.", reply_markup=get_main_menu()
        )
        return

    raw = message.text.strip()

    if field == "year":
        if not raw.isdigit() or not (1900 <= int(raw) <= 2100):
            await message.answer("Год — число от 1900 до 2100. Попробуй снова.")
            return
        value = int(raw)
    elif field == "mileage":
        cleaned = raw.replace(" ", "").replace(",", "")
        if not cleaned.isdigit():
            await message.answer("Пробег — число. Попробуй снова.")
            return
        value = int(cleaned)
    elif field == "license_plate":
        value = normalize_license_plate(raw)
    else:
        value = raw

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car = await get_active_car(user["id"])
    if car is None:
        await state.clear()
        await message.answer("Машина не найдена.", reply_markup=get_main_menu())
        return

    await update_car_field(car["id"], field, value)
    await state.clear()

    # Читаем обновлённую машину и показываем сводку
    car = await get_active_car(user["id"])
    text = (
        "✅ Обновлено.\n\n"
        f"🚗 <b>{car['brand']} {car['model']}</b>\n"
        f"Год: {car['year'] or '—'}\n"
        f"Двигатель: {car['engine'] or '—'}\n"
        f"VIN: {car['vin'] or '—'}\n"
        f"Пробег: {car['mileage']:,} км"
    )
    await message.answer(text, reply_markup=get_main_menu())


# ============ СЛУЖЕБНОЕ ============


@router.message(F.text == "↩️ В меню")
async def back_to_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню.", reply_markup=get_main_menu())


@router.message(Command("cancel"))
async def cancel_any(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Отменено.", reply_markup=get_main_menu())


# ============ ИНТЕРВАЛ ЗАМЕНЫ МАСЛА ============


@router.message(F.text == "⚙️ Настроить ТО")
async def ask_oil_interval(message: Message, state: FSMContext):
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car = await get_active_car(user["id"])
    if car is None:
        await message.answer("Сначала добавь машину.")
        return

    current = car["oil_interval_km"]
    hint = f"Сейчас: {current:,} км.\n\n".replace(",", " ") if current else ""

    await state.set_state(SetOilInterval.value)
    await message.answer(
        f"{hint}"
        "Через сколько километров ты меняешь моторное масло?\n"
        "Обычно это 8 000 – 15 000 км в зависимости от масла и условий.\n\n"
        "Введи число (например, <code>10000</code>).\n"
        "Чтобы отменить — /cancel.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(SetOilInterval.value)
async def save_oil_interval(message: Message, state: FSMContext):
    raw = message.text.strip().replace(" ", "")
    if not raw.isdigit() or not (1000 <= int(raw) <= 50000):
        await message.answer("Введи число от 1 000 до 50 000. Попробуй снова.")
        return

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    car = await get_active_car(user["id"])
    if car is None:
        await state.clear()
        await message.answer("Машина не найдена.", reply_markup=get_main_menu())
        return

    await update_car_field(car["id"], "oil_interval_km", int(raw))
    await state.clear()
    await message.answer(
        f"✅ Интервал сохранён: <b>{int(raw):,} км</b>.\n\n"
        "Теперь в Mini App будет показываться счётчик до следующей замены масла.".replace(
            ",", " "
        ),
        reply_markup=get_main_menu(),
    )
