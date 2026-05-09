from loguru import logger

from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.features.history.search import search_chat_history


async def search_chat_history_tool(
    recorder: OpenSearchRecorder,
    chat_id: int,
    query: str,
) -> str:

    logger.info(f"Searching chat history, {chat_id=}, {query=}")

    result = await search_chat_history(
        recorder.client,
        recorder.index,
        chat_id=chat_id,
        query_embedding=await recorder.embed_query(query),
        limit=10,
    )
    return result or "No matching chat history found"
