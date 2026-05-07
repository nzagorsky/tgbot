import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    telegram_token: str
    trigger_keyword: str
    opensearch_url: str
    opensearch_index: str
    opensearch_username: str | None
    opensearch_password: str | None
    opensearch_verify_certs: bool


def load_config() -> BotConfig:
    missing = [
        name
        for name in ("TELEGRAM_BOT_TOKEN", "TG_TRIGGER_KEYWORD", "OPENSEARCH_URL", "OPENSEARCH_INDEX")
        if not os.environ.get(name)
    ]
    if missing:
        raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")

    return BotConfig(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        trigger_keyword=os.environ["TG_TRIGGER_KEYWORD"],
        opensearch_url=os.environ["OPENSEARCH_URL"],
        opensearch_index=os.environ["OPENSEARCH_INDEX"],
        opensearch_username=os.environ.get("OPENSEARCH_USERNAME"),
        opensearch_password=os.environ.get("OPENSEARCH_PASSWORD"),
        opensearch_verify_certs=os.environ.get("OPENSEARCH_VERIFY_CERTS", "true").casefold()
        not in {"0", "false", "no"},
    )
