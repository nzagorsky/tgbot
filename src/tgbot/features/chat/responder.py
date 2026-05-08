from telegram import Message


async def respond(text: str, recent_messages: list[Message]) -> str | None:
    return await generate_reply(text, recent_messages)


async def generate_reply(text: str, recent_messages: list[Message]) -> str:
    return "This is generated"
