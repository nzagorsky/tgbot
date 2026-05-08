from collections import defaultdict, deque

from telegram import Message


class InMemoryChatBuffer:
    def __init__(self, *, limit: int = 50) -> None:
        self.messages: dict[int, deque[Message]] = defaultdict(lambda: deque(maxlen=limit))

    async def append(self, message: Message) -> None:
        self.messages[message.chat.id].append(message)

    async def recent(self, chat_id: int) -> list[Message]:
        return list(self.messages[chat_id])
