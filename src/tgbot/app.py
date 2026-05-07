from telegram.ext import Application, MessageHandler, filters

from tgbot.features.chat.handler import ChatDeps, listen


def build_app(token: str, chat_deps: ChatDeps) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["chat_deps"] = chat_deps
    app.add_handler(MessageHandler(filters.ALL, listen))
    return app
