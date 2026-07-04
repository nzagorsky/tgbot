from telegram import Message, Update
from telegram.ext import ContextTypes

from tgbot.features.chat.responder import respond
from tgbot.features.chat.types import ChatDeps


async def listen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message: Message | None = update.effective_message
    if message is None:
        return

    deps: ChatDeps = context.application.bot_data["chat_deps"]
    text = message.text or message.caption or ""
    matched_keyword = deps.trigger_keyword.casefold() in text.casefold()

    await deps.recorder.record(message)
    await deps.buffer.append(message)

    user = message.from_user

    if user and user.is_bot:
        return

    # Allow private conversations without matched keyword
    if not matched_keyword and not message.chat.type == message.chat.PRIVATE:
        return

    reply = await respond(
        text,
        await deps.buffer.recent(message.chat.id),
        chat_id=message.chat.id,
        recorder=deps.recorder,
        openrouter_api_key=deps.openrouter_api_key,
        searxng_url=deps.searxng_url,
    )
    if reply is None:
        return

    sent_message: Message = await message.reply_text(reply)
    await deps.recorder.record(sent_message)
    await deps.buffer.append(sent_message)
