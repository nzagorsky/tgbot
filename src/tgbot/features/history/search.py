from typing import Any
from loguru import logger

from opensearchpy import AsyncOpenSearch


async def search_chat_history(
    client: AsyncOpenSearch, index: str, *, chat_id: int, query: str, limit: int = 10
) -> str:
    response = await client.search(
        index=index,
        body={
            "size": limit,
            "query": {
                "bool": {
                    "filter": [{"term": {"chat_id": chat_id}}],
                    "must": [{"match": {"text": query}}],
                }
            },
        },
    )

    messages = []
    for hit in response["hits"]["hits"]:
        source: dict[str, Any] = hit["_source"]
        messages.append(
            f"[{source.get('timestamp', '')}] "
            f"{source.get('username') or 'unknown'}: {source.get('text', '')}"
        )

    logger.info("search_chat_history returned {} messages", len(messages))
    return "\n".join(messages)
