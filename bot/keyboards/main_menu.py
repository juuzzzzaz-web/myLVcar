"""Клавиатуры для бота."""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    """Главное меню бота: нижняя клавиатура с основными действиями."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚗 Моё авто")],
            [
                KeyboardButton(text="📝 Записи"),
                KeyboardButton(text="📄 Документы"),
            ],
            [KeyboardButton(text="🤖 AI-помощник")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие или напиши сообщение",
    )
    return keyboard
