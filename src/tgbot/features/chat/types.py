from dataclasses import dataclass

from tgbot.features.chat.buffer import InMemoryChatBuffer
from tgbot.features.history.opensearch import OpenSearchRecorder


@dataclass(frozen=True)
class ChatDeps:
    recorder: OpenSearchRecorder
    buffer: InMemoryChatBuffer
    trigger_keyword: str
    openrouter_api_key: str
    searxng_url: str
