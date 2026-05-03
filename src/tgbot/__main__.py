import logging
import os
import sys

from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss.SSS} {level} {name}: {message}")
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO, force=True)


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Hello. I am alive and polling.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Commands: /hello, /help")


def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", hello))
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("help", help_command))
    return app


def main() -> None:
    configure_logging()

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")

    build_app(token).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
