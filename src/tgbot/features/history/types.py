from dataclasses import dataclass

from tgbot.features.history.opensearch import OpenSearchRecorder


@dataclass
class UserContext:
    chat_id: int
    recorder: OpenSearchRecorder
