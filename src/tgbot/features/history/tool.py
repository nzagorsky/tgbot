from typing import Any

from loguru import logger

from tgbot.features.history.search import search_chat_history
from tgbot.llm.tools import Tool, ToolContext, ToolInputError

SEARCH_CHAT_HISTORY_TOOL_NAME = "search_chat_history"

async def run_search_chat_history_tool(arguments: dict[str, Any], context: ToolContext) -> str:
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ToolInputError("empty search query")

    recorder = context["recorder"]
    chat_id = int(context["chat_id"])
    logger.info("Searching chat history for chat_id={} query={!r}", chat_id, query)

    result = await search_chat_history(
        recorder.client,
        recorder.index,
        chat_id=chat_id,
        query=query,
        limit=10,
    )
    return result or "No matching chat history found"


SEARCH_CHAT_HISTORY_TOOL = Tool(
    schema={
        "type": "function",
        "function": {
            "name": SEARCH_CHAT_HISTORY_TOOL_NAME,
            "description": "Search older messages not included in the recent chat context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for in the current chat history.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    handler=run_search_chat_history_tool,
)
