from telegram import Message

SYSTEM_PROMPT_VERSION = "chat-system-v2"

SYSTEM_PROMPT = """
You are a Telegram group chat bot.
Reply naturally and briefly. Reply in the same language as the user's latest message. If languages are mixed, use the predominant language. Use recent chat messages first.

Always use search tool to get a better context of the conversation.
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
