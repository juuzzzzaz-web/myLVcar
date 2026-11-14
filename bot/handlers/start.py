"""Обработчик команды /start и приветствия."""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
import os

from bot.keyboards.main_menu import get_main_menu
from services.db.queries import (
    get_or_create_user, 
    get_active_car, 
    log_event, 
    get_analytics_summary,
    get_db
) 

router = Router()
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://твой-домен.bothost.tech")

# ВАЖНО: Замени это число на свой Telegram ID (узнать можно в боте @userinfobot)
ADMIN_ID = 436704696 


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Приветствие, регистрация, аналитика и меню."""
    await state.clear()
    
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # Записываем событие в нашу локальную аналитику
    await log_event(message.from_user.id, "start_command")

    active_car = await get_active_car(user["id"])

    # Кнопки
    builder = InlineKeyboardBuilder()
    builder.button(text="🚗 Открыть MyCar", web_app=WebAppInfo(url=WEBAPP_URL))
    builder.button(text="📖 Инструкция", callback_data="show_instructions")
    builder.button(text="❤️ Поддержать проект", callback_data="show_donations")
    builder.adjust(1) # Каждая кнопка на новой строке

    if active_car is None:
        text = (
            f"Привет, {message.from_user.first_name}.\n\n"
            "Я Талос — твой личный хранитель истории автомобиля.\n"
            "Здесь мы собираем весь уход за машиной: от замены масла до расходов на топливо.\n\n"
            "<b>С чего начать:</b>\n"
            "1. Открой приложение.\n"
            "2. Добавь свой автомобиль.\n"
            "3. Внеси первую запись (например, последнюю заправку).\n\n"
            "Я на связи."
        )
    else:
        text = (
            f"С возвращением, {message.from_user.first_name}!\n\n"
            f"🚗 <b>{active_car['brand']} {active_car['model']}</b>\n"
            f"Пробег: {active_car['mileage']:,} км\n\n"
            "Что делаем сегодня?"
        )

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# ============ ОБРАБОТЧИКИ КНОПОК ============

@router.callback_query(F.data == "show_instructions")
async def show_instructions(callback: CallbackQuery):
    """Показывает краткую инструкцию."""
    text = (
        "📖 <b>Как пользоваться MyCar</b>\n\n"
        "<b>1. Добавление машины</b>\n"
        "В Mini App нажми на карточку авто, чтобы заполнить данные (VIN, пробег, объем двигателя). Чем больше данных, тем умнее Талос.\n\n"
        "<b>2. Запись расходов</b>\n"
        "Используй плитки на главном экране: Топливо, ТО, Запчасти. Вноси суммы и пробег — система сама посчитает статистику за месяц.\n\n"
        "<b>3. Общение с Талосом</b>\n"
        "Нажми на карточку «AI-помощник». Спрашивай его о чем угодно: когда менял масло, какие аналоги запчастей искать, не разводят ли тебя в сервисе.\n\n"
        "<b>4. Документы</b>\n"
        "Во вкладке «Документы» сохраняй данные ОСАГО и СТС. Бот сам напомнит, если срок действия подходит к концу."
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "show_donations")
async def show_donations(callback: CallbackQuery):
    """Показывает информацию о донатах."""
    # ВСТАВЬ СЮДА СВОЮ ССЫЛКУ С DONATIONALERTS (например, https://www.donationalerts.com/r/твой_ник)
    donate_url = "https://www.donationalerts.com/r/samiysladenkiy"  
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Перейти к оплате", url=donate_url)

    text = (
        "❤️ <b>Поддержка проекта</b>\n\n"
        "MyCar — это бесплатный проект, который я делаю сам. "
        "Мне не платят корпорации, здесь нет рекламы и скрытых подписок.\n\n"
        "Если Талос помогает тебе экономить время и нервы, ты можешь поддержать разработку. "
        "Любая сумма — это огромный вклад в развитие приложения.\n\n"
        "Спасибо, что ты со мной."
    )
    
    await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ============ АДМИН-ПАНЕЛЬ (СТАТИСТИКА) ============

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Секретная команда для просмотра статистики (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        return
    
    # Получаем данные из событий
    data = await get_analytics_summary()
    
    # Получаем общее количество юзеров из таблицы users
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        row = await cursor.fetchone()
        total_users = row[0] if row else 0

    # Получаем количество уникальных пользователей, которые заходили в Mini App (если надо)
    # Можно добавить другие метрики.
    
    text = f"📊 <b>Статистика бота</b>\n\n"
    text += f"Всего аккаунтов в базе: <b>{total_users}</b>\n"
    text += f"Уникальных в аналитике: <b>{data['unique_users']}</b>\n\n"
    text += "<b>События:</b>\n"
    
    if data["events"]:
        for event, count in data["events"].items():
            text += f"- {event}: {count}\n"
    else:
        text += "Пока нет событий."
        
    await message.answer(text, parse_mode="HTML")