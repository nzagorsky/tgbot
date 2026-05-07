from telegram import Update

from tgbot.app import build_app
from tgbot.config import load_config
from tgbot.features.chat.handler import ChatDeps
from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.logging import configure_logging


def main() -> None:
    configure_logging()
    config = load_config()
    recorder = OpenSearchRecorder(
        url=config.opensearch_url,
        index=config.opensearch_index,
        username=config.opensearch_username,
        password=config.opensearch_password,
        verify_certs=config.opensearch_verify_certs,
    )
    build_app(config.telegram_token, ChatDeps(recorder, config.trigger_keyword)).run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
