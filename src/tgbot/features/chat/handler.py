from dataclasses import dataclass

from telegram import Message, Update
from telegram.ext import ContextTypes

from tgbot.features.chat.buffer import InMemoryChatBuffer
from tgbot.features.chat.responder import respond
from tgbot.features.history.opensearch import OpenSearchRecorder


@dataclass(frozen=True)
class ChatDeps:
    recorder: OpenSearchRecorder
    buffer: InMemoryChatBuffer
    trigger_keyword: str


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
    if (user and user.is_bot) or not matched_keyword:
        return

    reply = await respond(text, await deps.buffer.recent(message.chat.id))
    if reply is None:
        return

    sent_message: Message = await message.reply_text(reply)
    await deps.recorder.record(sent_message)
    await deps.buffer.append(sent_message)
