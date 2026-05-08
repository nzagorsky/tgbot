from datetime import datetime, timezone
from typing import Any

from langchain_openai import OpenAIEmbeddings
from loguru import logger
from opensearchpy import AsyncOpenSearch
from telegram import Message

SCHEMA_VERSION = 2
EMBEDDING_BASE_URL = "https://openrouter.ai/api/v1"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


class OpenSearchRecorder:
    def __init__(
        self,
        *,
        url: str,
        index: str,
        openrouter_api_key: str,
        username: str | None = None,
        password: str | None = None,
        verify_certs: bool = True,
    ) -> None:
        self.index = index
        self.embedding_model = EMBEDDING_MODEL
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
            api_key=openrouter_api_key,  # type: ignore
            base_url=EMBEDDING_BASE_URL,
            default_headers={"X-OpenRouter-Title": "tgbot"},
            timeout=30,
        )
        self.client = AsyncOpenSearch(
            hosts=[url],
            http_auth=(username or "", password or "") if username or password else None,
            verify_certs=verify_certs,
        )

        self.index_ensured = False

    async def ensure_index(self) -> None:
        if self.index_ensured:
            return

        if await self.client.indices.exists(index=self.index):
            await self.client.indices.put_mapping(
                index=self.index,
                body=message_mapping(),
            )
            self.index_ensured = True
            return

        await self.client.indices.create(
            index=self.index,
            body={
                "settings": {"index": {"knn": True}},
                "mappings": message_mapping(),
            },
        )
        self.index_ensured = True

    async def record(self, message: Message) -> None:
        await self.ensure_index()

        timestamp = message.date or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        chat = message.chat
        user = message.from_user
        reply_to = message.reply_to_message
        document: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
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
        }
        if document["text"].strip():
            try:
                document["embedding_model"] = self.embedding_model
                document["text_embedding"] = await self.embed_query(document["text"])
            except Exception:
                document.pop("embedding_model", None)
                logger.exception("Failed to embed Telegram message for OpenSearch")

        try:
            await self.client.index(
                index=self.index,
                id=f"tg:{document['chat_id']}:{document['message_id']}",
                body=document,
            )
        except Exception:
            logger.exception("Failed to record Telegram message in OpenSearch")

    async def close(self) -> None:
        await self.client.close()

    async def embed_query(self, text: str) -> list[float]:
        return await self.embeddings.aembed_query(text)


def message_mapping() -> dict[str, Any]:
    return {
        "dynamic": "strict",
        "properties": {
            "schema_version": {"type": "integer"},
            "chat_id": {"type": "long"},
            "chat_type": {"type": "keyword"},
            "chat_title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "user_id": {"type": "long"},
            "username": {"type": "keyword"},
            "first_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "message_id": {"type": "long"},
            "reply_to_message_id": {"type": "long"},
            "timestamp": {"type": "date"},
            "text": {"type": "text"},
            "embedding_model": {"type": "keyword"},
            "text_embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIMENSIONS,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                },
            },
        },
    }
