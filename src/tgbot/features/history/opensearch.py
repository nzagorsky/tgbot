from datetime import datetime, timezone
from typing import Any

from loguru import logger
from opensearchpy import OpenSearch

SCHEMA_VERSION = 1


class OpenSearchRecorder:
    def __init__(
        self,
        *,
        url: str,
        index: str,
        username: str | None = None,
        password: str | None = None,
        verify_certs: bool = True,
    ) -> None:
        self.index = index
        self.client = OpenSearch(
            hosts=[url],
            http_auth=(username or "", password or "") if username or password else None,
            verify_certs=verify_certs,
        )

    def record(self, message: Any, direction: str, *, matched_keyword: bool) -> None:
        document = build_message_document(message, direction, matched_keyword=matched_keyword)
        try:
            self.client.index(
                index=self.index,
                id=f"tg:{document['chat_id']}:{document['message_id']}:{document['direction']}",
                body=document,
            )
        except Exception:
            logger.exception("Failed to record Telegram message in OpenSearch")


def build_message_document(message: Any, direction: str, *, matched_keyword: bool) -> dict[str, Any]:
    timestamp = message.date or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)

    chat = message.chat
    user = message.from_user
    reply_to = message.reply_to_message
    return {
        "schema_version": SCHEMA_VERSION,
        "direction": direction,
        "chat_id": chat.id,
        "chat_type": chat.type,
        "chat_title": chat.title,
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "first_name": user.first_name if user else None,
        "message_id": message.message_id,
        "reply_to_message_id": reply_to.message_id if reply_to else None,
        "timestamp": timestamp.isoformat(),
        "text": message.text or message.caption or "",
        "matched_keyword": matched_keyword,
    }
