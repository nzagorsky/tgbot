from telegram.ext import Application, MessageHandler, filters

from tgbot.features.chat.handler import listen
from tgbot.features.chat.types import ChatDeps


def build_app(token: str, chat_deps: ChatDeps) -> Application:
    app = Application.builder().token(token).post_shutdown(close_chat_deps).build()
    app.bot_data["chat_deps"] = chat_deps
    app.add_handler(MessageHandler(filters.ALL, listen))
    return app


async def close_chat_deps(app: Application) -> None:
    close = getattr(app.bot_data["chat_deps"].recorder, "close", None)
    if close is not None:
        await close()
