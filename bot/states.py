"""FSM-состояния для пошаговых диалогов."""

from aiogram.fsm.state import State, StatesGroup


class AddCar(StatesGroup):
    """Пошаговое добавление машины."""
    brand = State()
    model = State()
    year = State()
    mileage = State()
    license_plate = State()   # ← добавили
    confirm = State()


class EditCar(StatesGroup):
    """Пошаговое редактирование машины."""

    choose_field = State()  # выбор, что редактируем
    new_value = State()  # ввод нового значения


class SetOilInterval(StatesGroup):
    """Установка интервала замены масла."""

    value = State()
