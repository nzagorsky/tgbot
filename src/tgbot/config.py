import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    telegram_token: str
    trigger_keyword: str
    openrouter_api_key: str
    searxng_url: str
    opensearch_url: str
    opensearch_index: str
    opensearch_username: str | None
    opensearch_password: str | None
    opensearch_verify_certs: bool


def load_config() -> BotConfig:
    missing = [
        name
        for name in (
            "TELEGRAM_BOT_TOKEN",
            "TG_TRIGGER_KEYWORD",
            "OPENROUTER_API_KEY",
            "SEARXNG_URL",
            "OPENSEARCH_URL",
        )
        if not os.environ.get(name)
    ]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

    return BotConfig(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        trigger_keyword=os.environ["TG_TRIGGER_KEYWORD"],
        openrouter_api_key=os.environ["OPENROUTER_API_KEY"],
        searxng_url=os.environ["SEARXNG_URL"],
        opensearch_url=os.environ["OPENSEARCH_URL"],
        opensearch_index="messages",
        opensearch_username=os.environ.get("OPENSEARCH_USERNAME"),
        opensearch_password=os.environ.get("OPENSEARCH_PASSWORD"),
        opensearch_verify_certs=os.environ.get("OPENSEARCH_VERIFY_CERTS", "true").casefold()
        not in {"0", "false", "no"},
    )
