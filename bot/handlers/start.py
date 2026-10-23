"""Обработчик команды /start."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext  # ← новая строка

from bot.keyboards.main_menu import get_main_menu
from services.db.queries import get_or_create_user, get_active_car

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):  # ← добавили state
    """Приветствие и регистрация пользователя."""
    await state.clear()  # ← сбрасываем FSM
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    active_car = await get_active_car(user["id"])

    if active_car is None:
        await message.answer(
            f"Привет, {message.from_user.first_name}!\n\n"
            "Я MyCar — твой дневник ухода за автомобилем.\n\n"
            "Пока у тебя нет добавленной машины. "
            "Давай начнём — добавь первую.",
            reply_markup=get_main_menu(),
        )
    else:
        await message.answer(
            f"С возвращением, {message.from_user.first_name}!\n\n"
            f"🚗 <b>{active_car['brand']} {active_car['model']}</b> "
            f"({active_car['year']})\n"
            f"Пробег: {active_car['mileage']:,} км\n\n"
            "Что делаем сегодня?",
            reply_markup=get_main_menu(),
        )
