import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers_admin import register_admin_handlers
from handlers_user import register_user_handlers
import database as db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
async def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found in .env file.")
        exit(1)

    db.init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    register_user_handlers(dp)
    register_admin_handlers(dp)

    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")
