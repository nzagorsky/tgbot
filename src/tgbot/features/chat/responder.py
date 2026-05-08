from typing import Any

import httpx
from loguru import logger
from telegram import Message

from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.features.history.tool import SEARCH_CHAT_HISTORY_TOOL, SEARCH_CHAT_HISTORY_TOOL_NAME
from tgbot.llm.tools import run_tool_calls

OPENROUTER_MODEL = "google/gemini-2.5-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOOL_CALLS = 3

SYSTEM_PROMPT = """You are a Telegram group chat bot.
Reply naturally and briefly.
Use search_chat_history when older chat context would help.
Do not claim you searched unless you used the tool.
If context is insufficient, ask one short clarifying question.
Do not use Markdown unless it makes the reply clearer."""

AVAILABLE_TOOLS = {SEARCH_CHAT_HISTORY_TOOL_NAME: SEARCH_CHAT_HISTORY_TOOL}

async def respond(
    text: str,
    recent_messages: list[Message],
    *,
    chat_id: int,
    recorder: OpenSearchRecorder,
    openrouter_api_key: str,
) -> str | None:
    try:
        return await generate_reply(
            text,
            recent_messages,
            chat_id=chat_id,
            recorder=recorder,
            openrouter_api_key=openrouter_api_key,
        )
    except Exception:
        logger.exception("Failed to generate chat reply")
        return None


async def generate_reply(
    text: str,
    recent_messages: list[Message],
    *,
    chat_id: int,
    recorder: OpenSearchRecorder,
    openrouter_api_key: str,
) -> str | None:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Recent chat messages:\n{format_recent_messages(recent_messages)}\n\nReply to:\n{text}",
        },
    ]
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "X-OpenRouter-Title": "tgbot",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(MAX_TOOL_CALLS + 1):
            message = await request_completion(client, headers, messages)
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                content = message.get("content")
                return content.strip() if isinstance(content, str) and content.strip() else None

            messages.extend(
                await run_tool_calls(
                    tool_calls,
                    tools=AVAILABLE_TOOLS,
                    context={"recorder": recorder, "chat_id": chat_id},
                )
            )

    logger.warning("OpenRouter tool loop exceeded {} calls", MAX_TOOL_CALLS)
    return None


async def request_completion(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    response = await client.post(
        OPENROUTER_URL,
        headers=headers,
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "tools": [tool.schema for tool in AVAILABLE_TOOLS.values()],
            "tool_choice": "auto",
            "temperature": 0.7,
            "max_tokens": 800,
        },
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]


def format_recent_messages(recent_messages: list[Message]) -> str:
    lines = []
    for message in recent_messages[-30:]:
        user = message.from_user
        author = user.username or user.first_name if user else "unknown"
        body = message.text or message.caption or ""
        if body:
            lines.append(f"{author}: {body}")
    return "\n".join(lines) or "No recent text messages"
