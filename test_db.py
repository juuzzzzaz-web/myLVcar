"""Расширенный тест: проверяем базу и функции из queries.py."""

import asyncio

from services.db.connection import init_db, close_db
from services.db.queries import (
    get_or_create_user,
    add_car,
    get_user_cars,
    get_active_car,
    set_active_car,
    add_record,
    get_records,
    get_fuel_stats,
)


async def main():
    await init_db()

    # 1. Создаём пользователя
    user = await get_or_create_user(987654321, "prota", "Прота")
    print("[OK] Пользователь:", user["id"], user["first_name"])

    # 2. Создаём первую машину — должна стать активной
    car1_id = await add_car(
        user_id=user["id"],
        brand="Toyota",
        model="Camry",
        year=2020,
        engine="2.5 AT",
        vin="XXXXXX123456",
        mileage=78420,
    )
    print(f"[OK] Машина 1 создана, id={car1_id}")

    # 3. Создаём вторую — должна быть неактивной
    car2_id = await add_car(
        user_id=user["id"],
        brand="Lada",
        model="Vesta",
        year=2018,
        mileage=120000,
    )
    print(f"[OK] Машина 2 создана, id={car2_id}")

    # 4. Проверяем, что первая — активная
    active = await get_active_car(user["id"])
    print(f"[OK] Активная машина: {active['brand']} {active['model']}")

    # 5. Переключаем активную на вторую
    await set_active_car(user["id"], car2_id)
    active = await get_active_car(user["id"])
    print(f"[OK] После переключения активная: {active['brand']} {active['model']}")

    # 6. Добавляем заправки для Camry
    await add_record(
        car_id=car1_id,
        record_type="fuel",
        date="2026-10-05",
        mileage=78000,
        cost=2800,
        data={"liters": 45, "price_per_liter": 62.2, "fuel_type": "АИ-95"},
    )
    await add_record(
        car_id=car1_id,
        record_type="fuel",
        date="2026-10-15",
        mileage=78420,
        cost=2600,
        data={"liters": 42, "price_per_liter": 61.9, "fuel_type": "АИ-95"},
    )
    await add_record(
        car_id=car1_id,
        record_type="part",
        date="2026-10-12",
        mileage=76800,
        cost=3500,
        description="Замена воздушного фильтра",
        data={"part_name": "фильтр воздушный", "brand": "Mann"},
    )
    print("[OK] Записи добавлены")

    # 7. Читаем все записи
    records = await get_records(car1_id)
    print(f"[OK] Всего записей у Camry: {len(records)}")

    # 8. Читаем только заправки
    fuels = await get_records(car1_id, record_type="fuel")
    print(f"[OK] Заправок: {len(fuels)}")

    # 9. Считаем статистику за октябрь 2026
    stats = await get_fuel_stats(car1_id, year=2026, month=10)
    print(f"[OK] Топливо за октябрь: {stats}")

    await close_db()
    print("[OK] Готово")


if __name__ == "__main__":
    asyncio.run(main())
