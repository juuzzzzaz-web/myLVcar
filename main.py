"""Точка входа: запуск бота MyCar и FastAPI сервера одновременно. """
import asyncio
import logging
import os

import uvicorn
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.handlers import start, car
from services.db.connection import init_db, close_db
from services.scheduler import check_daily_notifications  # Импортируем нашу функцию
from api.main import app as fastapi_app 

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def run_fastapi():
    """Запуск веб-сервера для Mini App."""
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    # 1. Инициализация базы данных
    await init_db()
    logger.info("База данных инициализирована")

    # 2. Создаем бота и диспетчер один раз для всего приложения
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(car.router)

    # 3. Настраиваем планировщик
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    # Запускать проверку каждый день в 10:00 утра
    scheduler.add_job(check_daily_notifications, 'cron', hour=10, minute=0, args=[bot])
    scheduler.start()
    logger.info("Планировщик уведомлений запущен")

    # 4. Запускаем всё вместе
    try:
        await asyncio.gather(
            run_fastapi(),
            dp.start_polling(bot)
        )
    finally:
        scheduler.shutdown()
        await bot.session.close()
        await close_db()
        logger.info("Приложение остановлено")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход по Ctrl+C")