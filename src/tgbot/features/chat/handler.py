from dataclasses import dataclass
from typing import Any, Protocol

from telegram import Update
from telegram.ext import ContextTypes

from tgbot.features.chat.responder import generate_reply


class MessageRecorder(Protocol):
    def record(self, message: Any, direction: str, *, matched_keyword: bool) -> None: ...


@dataclass(frozen=True)
class ChatDeps:
    recorder: MessageRecorder
    trigger_keyword: str


async def listen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    deps: ChatDeps = context.application.bot_data["chat_deps"]
    text = message.text or message.caption or ""
    matched_keyword = deps.trigger_keyword.casefold() in text.casefold()

    deps.recorder.record(message, "in", matched_keyword=matched_keyword)

    user = message.from_user
    if (user and user.is_bot) or not matched_keyword:
        return

    sent_message = await message.reply_text(await generate_reply(text))
    deps.recorder.record(sent_message, "out", matched_keyword=True)
