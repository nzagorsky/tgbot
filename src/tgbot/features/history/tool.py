from langchain.tools import ToolRuntime, tool
from loguru import logger

from tgbot.features.history.search import search_chat_history
from tgbot.features.history.types import UserContext


@tool
async def search_chat_history_tool(
    query: str,
    runtime: ToolRuntime[UserContext],
) -> str:
    """
    Search Telegram chat history for relevant context.

    Use this when the user asks about something that may have been discussed earlier.
    If the user asks multiple independent questions, call this separately for each question
    or use a query that targets the specific question being answered.
    """

    logger.info(f"TOOL: Searching chat history, {runtime.context.chat_id=}, {query=}")

    result = await search_chat_history(
        runtime.context.recorder.client,
        runtime.context.recorder.index,
        chat_id=runtime.context.chat_id,
        query_embedding=await runtime.context.recorder.embed_query(query),
        limit=10,
    )
    return result or "No matching chat history found"
