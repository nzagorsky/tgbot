from langchain.agents import create_agent as create_langchain_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from loguru import logger
from telegram import Message

from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.features.history.tool import UserContext, search_chat_history_tool
from tgbot.features.chat.prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION, render_user_prompt

OPENROUTER_MODEL = "google/gemini-2.5-flash"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_GRAPH_STEPS = 8


async def respond(
    text: str,
    recent_messages: list[Message],
    chat_id: int,
    recorder: OpenSearchRecorder,
    openrouter_api_key: str,
) -> str | None:

    try:
        chat_model = ChatOpenAI(
            model=OPENROUTER_MODEL,
            api_key=openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={"X-OpenRouter-Title": "tgbot"},
            temperature=0.7,
            max_tokens=800,  # type: ignore
            timeout=30,
        )

        agent = create_langchain_agent(
            chat_model,
            tools=[
                search_chat_history_tool,
            ],
            system_prompt=SYSTEM_PROMPT,
            context_schema=UserContext,
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=render_user_prompt(text, recent_messages))]},
            config={
                "recursion_limit": MAX_GRAPH_STEPS,
                "metadata": {
                    "model": OPENROUTER_MODEL,
                    "prompt_version": SYSTEM_PROMPT_VERSION,
                },
                "tags": ["telegram", "chat-reply", SYSTEM_PROMPT_VERSION],
            },
            context=UserContext(chat_id=chat_id, recorder=recorder),
        )
        messages = result.get("messages", [])

        for message in reversed(messages):
            if isinstance(message, AIMessage):
                content = message.content
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return None

    except Exception:
        logger.exception("Failed to generate chat reply")
        return None
