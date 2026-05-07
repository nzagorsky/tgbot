import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telegram.ext import MessageHandler

from tgbot.app import build_app
from tgbot.features.chat.handler import ChatDeps, listen
from tgbot.features.chat.responder import generate_reply
from tgbot.features.history.opensearch import OpenSearchRecorder, build_message_document


TRIGGER_KEYWORD = "trigger-keyword"


class FakeRecorder:
    async def record(self, message, direction: str, *, matched_keyword: bool) -> None:
        pass


class CapturingRecorder:
    def __init__(self) -> None:
        self.records = []

    async def record(self, message, direction: str, *, matched_keyword: bool) -> None:
        self.records.append((message, direction, matched_keyword))


def test_build_app_registers_message_listener() -> None:
    deps = ChatDeps(FakeRecorder(), TRIGGER_KEYWORD)
    app = build_app("123:ABC", deps)

    assert any(isinstance(handler, MessageHandler) for handler in app.handlers[0])
    assert app.bot_data["chat_deps"] == deps


def test_generate_reply_returns_placeholder() -> None:
    assert asyncio.run(generate_reply(f"{TRIGGER_KEYWORD}?")) == "This is generated"


def test_build_message_document_for_inbound_message() -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(id=123, type="group", title="Chat"),
        from_user=SimpleNamespace(id=456, username="person", first_name="Name"),
        reply_to_message=SimpleNamespace(message_id=788),
        message_id=789,
        date=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
        text=f"{TRIGGER_KEYWORD} hello",
        caption=None,
    )

    document = build_message_document(message, "in", matched_keyword=True)

    assert document == {
        "schema_version": 1,
        "direction": "in",
        "chat_id": 123,
        "chat_type": "group",
        "chat_title": "Chat",
        "user_id": 456,
        "username": "person",
        "first_name": "Name",
        "message_id": 789,
        "reply_to_message_id": 788,
        "timestamp": "2026-05-05T12:00:00+00:00",
        "text": f"{TRIGGER_KEYWORD} hello",
        "matched_keyword": True,
    }


def test_opensearch_recorder_uses_deterministic_document_id() -> None:
    client = CapturingOpenSearchClient()
    recorder = OpenSearchRecorder.__new__(OpenSearchRecorder)
    recorder.client = client
    recorder.index = "tg-messages"

    asyncio.run(recorder.record(make_message("hello"), "in", matched_keyword=False))

    assert client.records[0]["index"] == "tg-messages"
    assert client.records[0]["id"] == "tg:123:789:in"
    assert client.records[0]["body"]["text"] == "hello"


def test_listen_records_non_keyword_message_without_reply() -> None:
    recorder = CapturingRecorder()
    message = make_message("just chatting")
    update = SimpleNamespace(effective_message=message)
    context = make_context(recorder)

    asyncio.run(listen(update, context))

    assert [(direction, matched) for _, direction, matched in recorder.records] == [("in", False)]
    assert message.replies == []


def test_listen_records_bot_message_without_reply() -> None:
    recorder = CapturingRecorder()
    message = make_message(f"{TRIGGER_KEYWORD} from another bot")
    message.from_user.is_bot = True
    update = SimpleNamespace(effective_message=message)
    context = make_context(recorder)

    asyncio.run(listen(update, context))

    assert [(direction, matched) for _, direction, matched in recorder.records] == [("in", True)]
    assert message.replies == []


def test_listen_records_inbound_and_outbound_for_keyword_message() -> None:
    recorder = CapturingRecorder()
    message = make_message(f"{TRIGGER_KEYWORD} ping")
    update = SimpleNamespace(effective_message=message)
    context = make_context(recorder)

    asyncio.run(listen(update, context))

    assert [(direction, matched) for _, direction, matched in recorder.records] == [
        ("in", True),
        ("out", True),
    ]
    assert message.replies == ["This is generated"]


def make_context(recorder: CapturingRecorder) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(
            bot_data={"chat_deps": ChatDeps(recorder, TRIGGER_KEYWORD)},
        )
    )


class CapturingOpenSearchClient:
    def __init__(self) -> None:
        self.records = []

    async def index(self, *, index: str, id: str, body: dict) -> None:
        self.records.append({"index": index, "id": id, "body": body})


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
