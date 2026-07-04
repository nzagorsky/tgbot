from telegram import Update

from tgbot.app import build_app
from tgbot.config import load_config
from tgbot.features.chat.buffer import InMemoryChatBuffer
from tgbot.features.chat.types import ChatDeps
from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.logging import configure_logging


def main() -> None:
    configure_logging()
    config = load_config()
    recorder = OpenSearchRecorder(
        url=config.opensearch_url,
        index=config.opensearch_index,
        openrouter_api_key=config.openrouter_api_key,
        username=config.opensearch_username,
        password=config.opensearch_password,
        verify_certs=config.opensearch_verify_certs,
    )

    app = build_app(
        token=config.telegram_token,
        chat_deps=ChatDeps(
            recorder=recorder,
            buffer=InMemoryChatBuffer(limit=50),
            trigger_keyword=config.trigger_keyword,
            openrouter_api_key=config.openrouter_api_key,
            searxng_url=config.searxng_url,
        ),
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
