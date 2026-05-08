import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telegram.ext import MessageHandler

from tgbot.app import build_app
from tgbot.features.chat.buffer import InMemoryChatBuffer
from tgbot.features.chat.handler import ChatDeps, listen
from tgbot.features.chat.responder import generate_reply, respond
from tgbot.features.history.opensearch import OpenSearchRecorder
from tgbot.features.history.search import search_chat_history


TRIGGER_KEYWORD = "trigger-keyword"


class FakeRecorder:
    async def record(self, message) -> None:
        pass


class CapturingRecorder:
    def __init__(self) -> None:
        self.records = []

    async def record(self, message) -> None:
        self.records.append(message)


def test_build_app_registers_message_listener() -> None:
    deps = ChatDeps(FakeRecorder(), InMemoryChatBuffer(), TRIGGER_KEYWORD)
    app = build_app("123:ABC", deps)

    assert any(isinstance(handler, MessageHandler) for handler in app.handlers[0])
    assert app.bot_data["chat_deps"] == deps


def test_generate_reply_returns_placeholder() -> None:
    assert asyncio.run(generate_reply(f"{TRIGGER_KEYWORD}?", [])) == "This is generated"


def test_opensearch_recorder_uses_deterministic_document_id() -> None:
    client = CapturingOpenSearchClient()
    recorder = OpenSearchRecorder.__new__(OpenSearchRecorder)
    recorder.client = client
    recorder.index = "tg-messages"

    asyncio.run(recorder.record(make_message("hello")))

    assert client.records[0]["index"] == "tg-messages"
    assert client.records[0]["id"] == "tg:123:789"
    assert client.records[0]["body"]["text"] == "hello"


def test_listen_records_non_keyword_message_without_reply(monkeypatch) -> None:
    recorder = CapturingRecorder()
    buffer = InMemoryChatBuffer()
    requests = []
    message = make_message("just chatting")
    update = SimpleNamespace(effective_message=message)

    async def capture_respond(text: str, recent_messages: list) -> str | None:
        requests.append((text, recent_messages))
        return "This is generated"

    monkeypatch.setattr("tgbot.features.chat.handler.respond", capture_respond)
    context = make_context(recorder, buffer=buffer)

    asyncio.run(listen(update, context))

    assert [message.text for message in recorder.records] == ["just chatting"]
    assert [message.text for message in asyncio.run(buffer.recent(message.chat.id))] == ["just chatting"]
    assert requests == []
    assert message.replies == []


def test_listen_records_bot_message_without_reply(monkeypatch) -> None:
    recorder = CapturingRecorder()
    buffer = InMemoryChatBuffer()
    requests = []
    message = make_message(f"{TRIGGER_KEYWORD} from another bot")
    message.from_user.is_bot = True
    update = SimpleNamespace(effective_message=message)

    async def capture_respond(text: str, recent_messages: list) -> str | None:
        requests.append((text, recent_messages))
        return "This is generated"

    monkeypatch.setattr("tgbot.features.chat.handler.respond", capture_respond)
    context = make_context(recorder, buffer=buffer)

    asyncio.run(listen(update, context))

    assert [message.text for message in recorder.records] == [f"{TRIGGER_KEYWORD} from another bot"]
    assert [message.text for message in asyncio.run(buffer.recent(message.chat.id))] == [
        f"{TRIGGER_KEYWORD} from another bot"
    ]
    assert requests == []
    assert message.replies == []


def test_listen_records_inbound_and_outbound_for_keyword_message(monkeypatch) -> None:
    recorder = CapturingRecorder()
    buffer = InMemoryChatBuffer()
    requests = []
    message = make_message(f"{TRIGGER_KEYWORD} ping")
    update = SimpleNamespace(effective_message=message)

    async def capture_respond(text: str, recent_messages: list) -> str | None:
        requests.append((text, recent_messages))
        return "This is generated"

    monkeypatch.setattr("tgbot.features.chat.handler.respond", capture_respond)
    context = make_context(recorder, buffer=buffer)

    asyncio.run(listen(update, context))

    assert [message.text for message in recorder.records] == [
        f"{TRIGGER_KEYWORD} ping",
        "This is generated",
    ]
    assert requests[0][0] == f"{TRIGGER_KEYWORD} ping"
    assert [message.text for message in requests[0][1]] == [f"{TRIGGER_KEYWORD} ping"]
    assert [message.text for message in asyncio.run(buffer.recent(message.chat.id))] == [
        f"{TRIGGER_KEYWORD} ping",
        "This is generated",
    ]
    assert message.replies == ["This is generated"]


def test_listen_ignores_update_without_message() -> None:
    recorder = CapturingRecorder()
    update = SimpleNamespace(effective_message=None)
    context = make_context(recorder)

    asyncio.run(listen(update, context))

    assert recorder.records == []


def test_respond_keeps_current_placeholder_reply() -> None:
    reply = asyncio.run(respond(f"{TRIGGER_KEYWORD}?", []))

    assert reply == "This is generated"


def test_search_chat_history_filters_to_current_chat() -> None:
    client = CapturingOpenSearchSearchClient()

    result = asyncio.run(
        search_chat_history(client, "tg-messages", chat_id=123, query="deploy", limit=3)
    )

    assert client.searches == [
        {
            "index": "tg-messages",
            "body": {
                "size": 3,
                "query": {
                    "bool": {
                        "filter": [{"term": {"chat_id": 123}}],
                        "must": [{"match": {"text": "deploy"}}],
                    }
                },
            },
        }
    ]
    assert result == "[2026-05-05T12:00:00+00:00] person: deploy notes"


def make_context(
    recorder: CapturingRecorder,
    *,
    buffer: InMemoryChatBuffer | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "chat_deps": ChatDeps(recorder, buffer or InMemoryChatBuffer(), TRIGGER_KEYWORD)
            },
        )
    )


class CapturingOpenSearchClient:
    def __init__(self) -> None:
        self.records = []

    async def index(self, *, index: str, id: str, body: dict) -> None:
        self.records.append({"index": index, "id": id, "body": body})


class CapturingOpenSearchSearchClient:
    def __init__(self) -> None:
        self.searches = []

    async def search(self, *, index: str, body: dict) -> dict:
        self.searches.append({"index": index, "body": body})
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "username": "person",
                            "text": "deploy notes",
                            "timestamp": "2026-05-05T12:00:00+00:00",
                        }
                    }
                ]
            }
        }


def make_message(text: str) -> SimpleNamespace:
    message = SimpleNamespace(
        chat=SimpleNamespace(id=123, type="group", title="Chat"),
        from_user=SimpleNamespace(id=456, username="person", first_name="Name", is_bot=False),
        reply_to_message=None,
        message_id=789,
        date=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        text=text,
        caption=None,
        replies=[],
    )

    async def reply_text(reply: str) -> SimpleNamespace:
        message.replies.append(reply)
        return SimpleNamespace(
            chat=message.chat,
            from_user=SimpleNamespace(id=999, username="bot", first_name="Bot", is_bot=True),
            reply_to_message=message,
            message_id=790,
            date=datetime(2026, 5, 5, 12, 1, tzinfo=timezone.utc),
            text=reply,
            caption=None,
        )

    message.reply_text = reply_text
    return message
