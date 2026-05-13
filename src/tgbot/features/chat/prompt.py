from telegram import Message

from tgbot.config import load_config

config = load_config()

SYSTEM_PROMPT_VERSION = "chat-system-v2"

SYSTEM_PROMPT = f"""
You are a Telegram group chat bot. Your name is {config.trigger_keyword}
Reply naturally and briefly. Always reply. Never complain.
Reply in the same language as the user's latest message. If languages are mixed, use the predominant language. Use recent chat messages first.

Always use chat history search to get a better context of the conversation.
Use web search for current events, external facts, or anything that may have changed recently.
"""


def render_user_prompt(text: str, recent_messages: list[Message]) -> str:
    return f"Recent chat messages:\n{format_recent_messages(recent_messages)}\n\nReply to:\n{text}"


def format_recent_messages(recent_messages: list[Message]) -> str:
    lines = []
    for message in recent_messages[-30:]:
        user = message.from_user
        author = user.username or user.first_name if user else "unknown"
        body = message.text or message.caption or ""
        if body:
            lines.append(f"{author}: {body}")
    return "\n".join(lines) or "No recent text messages"
