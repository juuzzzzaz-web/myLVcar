"""Точка входа: запуск бота MyCar и FastAPI сервера одновременно."""
import asyncio
import logging
import os

import uvicorn
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import start, car
from services.db.connection import init_db, close_db
from api.main import app as fastapi_app  # Импортируем приложение FastAPI

# Загружаем переменные окружения (на сервере их подставит BotHost)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def run_fastapi():
    """Запуск веб-сервера для Mini App."""
    # BotHost обычно передает порт через переменную окружения PORT
    port = int(os.getenv("PORT", 8000))
    config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def run_bot():
    """Запуск Telegram-бота."""
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(car.router)

    logger.info("Бот запущен (polling)")
    await dp.start_polling(bot)

async def main():
    # Инициализация базы данных
    await init_db()
    logger.info("База данных инициализирована")

    # Запускаем FastAPI и бота параллельно
    try:
        await asyncio.gather(
            run_fastapi(),
            run_bot()
        )
    finally:
        await close_db()
        logger.info("Приложение остановлено")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход по Ctrl+C")