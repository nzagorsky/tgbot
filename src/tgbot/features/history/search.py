from typing import Any

from loguru import logger
from opensearchpy import AsyncOpenSearch


async def search_chat_history(
    client: AsyncOpenSearch,
    index: str,
    chat_id: int,
    query_embedding: list[float] | None = None,
    limit: int = 10,
) -> str:
    vector_response = {"hits": {"hits": []}}

    if not query_embedding:
        logger.info("Nothing found for query embedding")

    vector_response = await client.search(
        index=index,
        body={
            "size": limit,
            "query": {
                "knn": {
                    "text_embedding": {
                        "vector": query_embedding,
                        "k": max(limit * 3, limit),
                        "filter": {
                            "bool": {
                                "filter": [
                                    {"term": {"chat_id": chat_id}},
                                    {"exists": {"field": "text_embedding"}},
                                ]
                            }
                        },
                    }
                }
            },
        },
    )

    hits_by_id: dict[str, dict[str, Any]] = {}
    scores_by_id: dict[str, float] = {}
    for hit in vector_response.get("hits", {}).get("hits", []):
        document_id = str(hit.get("_id") or hit.get("_source", {}).get("message_id") or id(hit))
        hits_by_id.setdefault(document_id, hit)
        scores_by_id[document_id] = scores_by_id.get(document_id, 0.0) + float(
            hit.get("_score") or 0.0
        )

    messages = []
    for hit in sorted(
        hits_by_id.values(),
        key=lambda hit: (
            scores_by_id[
                str(hit.get("_id") or hit.get("_source", {}).get("message_id") or id(hit))
            ],
            hit.get("_source", {}).get("timestamp", ""),
        ),
        reverse=True,
    )[:limit]:
        source: dict[str, Any] = hit["_source"]
        if source.get("chat_id") != chat_id:
            logger.warning("Dropping search hit for unexpected chat_id={}", source.get("chat_id"))
            continue
        messages.append(
            f"[{source.get('timestamp', '')}] "
            f"{source.get('username') or 'unknown'}: {source.get('text', '')}"
        )

    logger.info("search_chat_history returned {} messages", len(messages))
    return "\n".join(messages)
