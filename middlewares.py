from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Update

from i18n import fetch_user_lang, is_lang_cached


class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user and not is_lang_cached(user.id):
            await fetch_user_lang(user.id)
            
        return await handler(event, data)
