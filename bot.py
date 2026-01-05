import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
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

    await db.init_db()

    # Use DefaultBotProperties for default settings (aiogram 3.24 best practice)
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    
    # Register global middleware to ensure language is cached
    from middlewares import LanguageMiddleware
    dp.update.outer_middleware(LanguageMiddleware())

    register_user_handlers(dp)
    register_admin_handlers(dp)

    print("Bot is running...")
    try:
        await dp.start_polling(bot)
    finally:
        # Properly close the bot session
        await bot.session.close()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")
