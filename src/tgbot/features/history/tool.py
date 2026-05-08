from typing import Any

from loguru import logger

from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.features.history.search import search_chat_history
from tgbot.llm.tools import Tool, ToolContext, ToolInputError

SEARCH_CHAT_HISTORY_TOOL_NAME = "search_chat_history"
SERVER_CONTROLLED_SCOPE_ARGUMENTS = {
    "chat_id",
    "chat",
    "index",
    "filter",
    "filters",
    "where",
}


async def run_search_chat_history_tool(arguments: dict[str, Any], context: ToolContext) -> str:
    if scope_arguments := SERVER_CONTROLLED_SCOPE_ARGUMENTS & set(arguments):
        raise ToolInputError(
            f"chat history scope is server-controlled: {', '.join(sorted(scope_arguments))}"
        )

    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ToolInputError("empty search query")

    recorder: OpenSearchRecorder = context["recorder"]
    chat_id = int(context["chat_id"])
    logger.info(f"Searching chat history, {chat_id=}, {query=}")

    result = await search_chat_history(
        recorder.client,
        recorder.index,
        chat_id=chat_id,
        query_embedding=await recorder.embed_query(query),
        limit=10,
    )
    return result or "No matching chat history found"


SEARCH_CHAT_HISTORY_TOOL = Tool(
    schema={
        "type": "function",
        "function": {
            "name": SEARCH_CHAT_HISTORY_TOOL_NAME,
            "description": "Semantically search older messages not included in the recent chat context.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text or concept to semantically search for in the current chat history.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    handler=run_search_chat_history_tool,
)
