import logging
from datetime import datetime
from aiogram import Bot
from services.db.connection import get_db
from services.db.queries import get_next_oil_change, get_documents

logger = logging.getLogger(__name__)

async def check_daily_notifications(bot: Bot):
    logger.info("Запуск проверки уведомлений...")
    db = await get_db()
    
    async with db.execute("""
        SELECT c.id as car_id, c.brand, c.model, u.telegram_id 
        FROM cars c 
        JOIN users u ON c.user_id = u.id 
        WHERE c.is_active = 1
    """) as cursor:
        cars = await cursor.fetchall()

    for car in cars:
        car = dict(car)
        telegram_id = car["telegram_id"]
        car_name = f"{car['brand']} {car['model']}"
        
        # 1. ПРОВЕРКА МАСЛА
        oil_data = await get_next_oil_change(car["car_id"])
        if oil_data and oil_data["km_left"] <= 1000:
            km_left = oil_data["km_left"]
            
            if km_left <= 0:
                text = (f"🛑 <b>Просрочена замена масла!</b>\n\n"
                        f"На твоей {car_name} замена масла просрочена на <b>{abs(km_left)} км</b>.\n\n"
                        f"Рекомендую не откладывать визит в сервис.")
            else:
                text = (f"🔧 <b>Скоро ТО</b>\n\n"
                        f"На твоей {car_name} подходит замена масла.\n"
                        f"Осталось: <b>{km_left} км</b>.\n\n"
                        f"Запиши замену в приложении, чтобы я не забыл.")
            
            try:
                await bot.send_message(telegram_id, text)
                logger.info(f"Уведомление о масле отправлено {telegram_id}")
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение {telegram_id}: {e}")

        # 2. ПРОВЕРКА ДОКУМЕНТОВ
        docs = await get_documents(car["car_id"])
        today = datetime.now().date()
        
        for doc in docs:
            if doc["expires_at"]:
                try:
                    exp_date = datetime.strptime(doc["expires_at"].split("T")[0], "%Y-%m-%d").date()
                    days_left = (exp_date - today).days
                    
                    if days_left <= 30:
                        if days_left < 0:
                            text = (f"🚨 <b>Документ просрочен!</b>\n\n"
                                    f"Документ {doc['type']} на {car_name} просрочен {abs(days_left)} дн. назад.\n"
                                    f"Срочно обнови его!")
                        else:
                            text = (f"📄 <b>Документы</b>\n\n"
                                    f"Документ {doc['type']} на {car_name} истекает через {days_left} дн.\n"
                                    f"Не забудь продлить.")
                        
                        try:
                            await bot.send_message(telegram_id, text)
                            logger.info(f"Уведомление о документе {doc['type']} отправлено {telegram_id}")
                        except Exception as e:
                            logger.error(f"Не удалось отправить сообщение {telegram_id}: {e}")
                except Exception as e:
                    logger.error(f"Ошибка парсинга даты документа: {e}")

    logger.info("Проверка уведомлений завершена.")