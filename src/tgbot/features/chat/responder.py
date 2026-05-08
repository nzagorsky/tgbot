import hashlib
from typing import Any

from langchain.agents import create_agent as create_langchain_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import BaseModel, Field
from telegram import Message

from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.features.history.tool import SEARCH_CHAT_HISTORY_TOOL_NAME, run_search_chat_history_tool
from tgbot.features.random.tool import RANDOM_NUMBER_TOOL_NAME, run_random_number_tool
from tgbot.features.chat.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION, render_user_prompt

OPENROUTER_MODEL = "google/gemini-2.5-flash"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_GRAPH_STEPS = 8


class SearchChatHistoryArgs(BaseModel):
    query: str = Field(description="Text to search for in the current chat history.")


class RandomNumberArgs(BaseModel):
    min: int = Field(1, description="Inclusive lower bound. Defaults to 1.")
    max: int = Field(100, description="Inclusive upper bound. Defaults to 100.")


def available_tools(*, recorder: OpenSearchRecorder, chat_id: int) -> list[StructuredTool]:
    async def search_chat_history(query: str) -> str:
        return await run_search_chat_history_tool(
            {"query": query},
            {"recorder": recorder, "chat_id": chat_id},
        )

    async def random_number(min: int = 1, max: int = 100) -> str:
        return await run_random_number_tool({"min": min, "max": max}, {})

    return [
        StructuredTool.from_function(
            coroutine=search_chat_history,
            name=SEARCH_CHAT_HISTORY_TOOL_NAME,
            description="Search older messages in the current Telegram chat history.",
            args_schema=SearchChatHistoryArgs,
        ),
        StructuredTool.from_function(
            coroutine=random_number,
            name=RANDOM_NUMBER_TOOL_NAME,
            description="Generate a random integer in an inclusive range.",
            args_schema=RandomNumberArgs,
        ),
    ]

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
    agent = create_agent(
        openrouter_api_key=openrouter_api_key,
        recorder=recorder,
        chat_id=chat_id,
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=render_user_prompt(text, recent_messages))]},
        config={
            "recursion_limit": MAX_GRAPH_STEPS,
            "metadata": {
                "chat_fingerprint": chat_fingerprint(chat_id),
                "model": OPENROUTER_MODEL,
                "prompt_version": SYSTEM_PROMPT_VERSION,
            },
            "tags": ["telegram", "chat-reply", SYSTEM_PROMPT_VERSION],
        },
    )
    return final_content(result.get("messages", []))


def create_agent(*, openrouter_api_key: str, recorder: OpenSearchRecorder, chat_id: int) -> Any:
    return create_langchain_agent(
        create_chat_model(openrouter_api_key),
        available_tools(recorder=recorder, chat_id=chat_id),
        system_prompt=SYSTEM_PROMPT,
    )


def create_chat_model(openrouter_api_key: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        api_key=openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={"X-OpenRouter-Title": "tgbot"},
        temperature=0.7,
        max_tokens=800,
        timeout=30,
    )


def final_content(messages: list[BaseMessage]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str) and content.strip():
                return content.strip()
    return None


def chat_fingerprint(chat_id: int) -> str:
    return hashlib.sha256(str(chat_id).encode()).hexdigest()[:12]
