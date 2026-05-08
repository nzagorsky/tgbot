import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from telegram.ext import MessageHandler

from tgbot.app import build_app
from tgbot.features.chat.buffer import InMemoryChatBuffer
from tgbot.features.chat.handler import ChatDeps, listen
from tgbot.features.chat.prompt import SYSTEM_PROMPT_VERSION
from tgbot.features.chat.responder import (
    OPENROUTER_MODEL,
    available_tools,
    chat_fingerprint,
    generate_reply,
    respond,
)
from tgbot.features.history.opensearch import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    OpenSearchRecorder,
)
from tgbot.features.history.search import search_chat_history
from tgbot.features.history.tool import SEARCH_CHAT_HISTORY_TOOL, SEARCH_CHAT_HISTORY_TOOL_NAME
from tgbot.features.random.tool import RANDOM_NUMBER_TOOL, RANDOM_NUMBER_TOOL_NAME
from tgbot.llm.tools import MAX_TOOL_RESULT_CHARS, run_tool_call


TRIGGER_KEYWORD = "trigger-keyword"
OPENROUTER_API_KEY = "openrouter-key"
HISTORY_TOOLS = {SEARCH_CHAT_HISTORY_TOOL_NAME: SEARCH_CHAT_HISTORY_TOOL}
RANDOM_TOOLS = {RANDOM_NUMBER_TOOL_NAME: RANDOM_NUMBER_TOOL}


class FakeRecorder:
    async def record(self, message) -> None:
        pass


class CapturingRecorder:
    def __init__(self) -> None:
        self.records = []

    async def record(self, message) -> None:
        self.records.append(message)


def test_build_app_registers_message_listener() -> None:
    deps = ChatDeps(FakeRecorder(), InMemoryChatBuffer(), TRIGGER_KEYWORD, OPENROUTER_API_KEY)
    app = build_app("123:ABC", deps)

    assert any(isinstance(handler, MessageHandler) for handler in app.handlers[0])
    assert app.bot_data["chat_deps"] == deps


def test_generate_reply_returns_openrouter_message(monkeypatch) -> None:
    agent = CapturingAgent("AI reply")
    monkeypatch.setattr("tgbot.features.chat.responder.create_agent", agent.factory)

    reply = asyncio.run(
        generate_reply(
            f"{TRIGGER_KEYWORD}?",
            [make_message("recent context")],
            chat_id=123,
            recorder=make_search_recorder(),
            openrouter_api_key=OPENROUTER_API_KEY,
        )
    )

    assert reply == "AI reply"
    assert agent.kwargs["openrouter_api_key"] == OPENROUTER_API_KEY
    assert agent.kwargs["chat_id"] == 123
    assert "recent context" in agent.inputs["messages"][0].content
    assert agent.config["metadata"] == {
        "chat_fingerprint": chat_fingerprint(123),
        "model": OPENROUTER_MODEL,
        "prompt_version": SYSTEM_PROMPT_VERSION,
    }


def test_available_tools_runs_search_history_tool() -> None:
    recorder = make_search_recorder()
    tools = available_tools(recorder=recorder, chat_id=123)

    result = asyncio.run(tools[0].ainvoke({"query": "deploy"}))

    assert result == "[2026-05-05T12:00:00+00:00] person: deploy notes"
    assert recorder.client.searches[0]["body"]["query"]["bool"]["must"] == [
        {"match": {"text": "deploy"}}
    ]
    assert recorder.client.searches[1]["body"]["query"]["knn"]["text_embedding"] == {
        "vector": [0.1, 0.2, 0.3],
        "k": 30,
        "filter": {
            "bool": {
                "filter": [
                    {"term": {"chat_id": 123}},
                    {"exists": {"field": "text_embedding"}},
                ]
            }
        },
    }


def test_generate_reply_returns_none_for_empty_final_message(monkeypatch) -> None:
    agent = CapturingAgent("   ")
    monkeypatch.setattr("tgbot.features.chat.responder.create_agent", agent.factory)

    reply = asyncio.run(
        generate_reply(
            f"{TRIGGER_KEYWORD} what about deploy?",
            [],
            chat_id=123,
            recorder=make_search_recorder(),
            openrouter_api_key=OPENROUTER_API_KEY,
        )
    )

    assert reply is None


def test_available_tools_runs_random_number_tool() -> None:
    tools = available_tools(recorder=make_search_recorder(), chat_id=123)

    result = asyncio.run(tools[1].ainvoke({"min": 1, "max": 10000000}))

    assert 1 <= int(result) <= 10000000


def test_run_tool_call_reports_unsupported_tool() -> None:
    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {"name": "unknown_tool", "arguments": "{}"},
            },
            tools=HISTORY_TOOLS,
            context={"recorder": make_search_recorder(), "chat_id": 123},
        )
    )

    assert result == {
        "role": "tool",
        "tool_call_id": "call-1",
        "name": "unknown_tool",
        "content": "Tool error: unsupported tool",
    }


def test_run_tool_call_reports_empty_search_query() -> None:
    recorder = make_search_recorder()

    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {"name": "search_chat_history", "arguments": '{"query": "   "}'},
            },
            tools=HISTORY_TOOLS,
            context={"recorder": recorder, "chat_id": 123},
        )
    )

    assert result["content"] == "Tool error: empty search query"
    assert recorder.client.searches == []


def test_run_tool_call_rejects_search_scope_arguments() -> None:
    recorder = make_search_recorder()

    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {
                    "name": "search_chat_history",
                    "arguments": '{"query": "deploy", "chat_id": 999}',
                },
            },
            tools=HISTORY_TOOLS,
            context={"recorder": recorder, "chat_id": 123},
        )
    )

    assert result["content"] == "Tool error: chat history scope is server-controlled: chat_id"
    assert recorder.client.searches == []


def test_run_tool_call_returns_random_number_in_range() -> None:
    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {"name": "random_number", "arguments": '{"min": 1, "max": 10000000}'},
            },
            tools=RANDOM_TOOLS,
            context={},
        )
    )

    assert result["name"] == "random_number"
    assert 1 <= int(result["content"]) <= 10000000


def test_run_tool_call_reports_invalid_random_number_range() -> None:
    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {"name": "random_number", "arguments": '{"min": 10, "max": 1}'},
            },
            tools=RANDOM_TOOLS,
            context={},
        )
    )

    assert result["content"] == "Tool error: min cannot be greater than max"


def test_run_tool_call_reports_search_failure() -> None:
    recorder = SimpleNamespace(
        client=FailingOpenSearchSearchClient(),
        index="tg-messages",
        embed_query=FakeEmbeddings().aembed_query,
    )

    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {"name": "search_chat_history", "arguments": '{"query": "deploy"}'},
            },
            tools=HISTORY_TOOLS,
            context={"recorder": recorder, "chat_id": 123},
        )
    )

    assert result["content"] == "Tool error: search_chat_history failed"


def test_run_tool_call_clamps_long_search_result() -> None:
    recorder = SimpleNamespace(
        client=LongOpenSearchSearchClient(),
        index="tg-messages",
        embed_query=FakeEmbeddings().aembed_query,
    )

    result = asyncio.run(
        run_tool_call(
            {
                "id": "call-1",
                "function": {"name": "search_chat_history", "arguments": '{"query": "deploy"}'},
            },
            tools=HISTORY_TOOLS,
            context={"recorder": recorder, "chat_id": 123},
        )
    )

    assert result["content"].endswith("\n[truncated]")
    assert len(result["content"]) == MAX_TOOL_RESULT_CHARS + len("\n[truncated]")


def test_opensearch_recorder_uses_deterministic_document_id() -> None:
    client = CapturingOpenSearchClient()
    recorder = OpenSearchRecorder.__new__(OpenSearchRecorder)
    recorder.client = client
    recorder.index = "tg-messages"
    recorder.embedding_model = EMBEDDING_MODEL
    recorder.embeddings = FakeEmbeddings()

    asyncio.run(recorder.record(make_message("hello")))

    assert client.records[0]["index"] == "tg-messages"
    assert client.records[0]["id"] == "tg:123:789"
    assert client.records[0]["body"]["text"] == "hello"
    assert client.records[0]["body"]["embedding_model"] == EMBEDDING_MODEL
    assert client.records[0]["body"]["text_embedding"] == [0.1, 0.2, 0.3]


def test_opensearch_recorder_initializes_index_mapping() -> None:
    client = CapturingOpenSearchClient(index_exists=False)
    recorder = OpenSearchRecorder.__new__(OpenSearchRecorder)
    recorder.client = client
    recorder.index = "tg-messages"

    asyncio.run(recorder.ensure_index())

    assert client.created_indices[0]["index"] == "tg-messages"
    assert client.created_indices[0]["body"]["settings"] == {"index": {"knn": True}}
    assert client.created_indices[0]["body"]["mappings"]["properties"]["text_embedding"] == {
        "type": "knn_vector",
        "dimension": EMBEDDING_DIMENSIONS,
        "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
    }


def test_listen_records_non_keyword_message_without_reply(monkeypatch) -> None:
    recorder = CapturingRecorder()
    buffer = InMemoryChatBuffer()
    requests = []
    message = make_message("just chatting")
    update = SimpleNamespace(effective_message=message)

    async def capture_respond(text: str, recent_messages: list, **kwargs) -> str | None:
        requests.append((text, recent_messages, kwargs))
        return "This is generated"

    monkeypatch.setattr("tgbot.features.chat.handler.respond", capture_respond)
    context = make_context(recorder, buffer=buffer)

    asyncio.run(listen(update, context))

    assert [message.text for message in recorder.records] == ["just chatting"]
    assert [message.text for message in asyncio.run(buffer.recent(message.chat.id))] == [
        "just chatting"
    ]
    assert requests == []
    assert message.replies == []


def test_listen_records_bot_message_without_reply(monkeypatch) -> None:
    recorder = CapturingRecorder()
    buffer = InMemoryChatBuffer()
    requests = []
    message = make_message(f"{TRIGGER_KEYWORD} from another bot")
    message.from_user.is_bot = True
    update = SimpleNamespace(effective_message=message)

    async def capture_respond(text: str, recent_messages: list, **kwargs) -> str | None:
        requests.append((text, recent_messages, kwargs))
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

    async def capture_respond(text: str, recent_messages: list, **kwargs) -> str | None:
        requests.append((text, recent_messages, kwargs))
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
    assert requests[0][2] == {
        "chat_id": 123,
        "recorder": recorder,
        "openrouter_api_key": OPENROUTER_API_KEY,
    }
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


def test_respond_returns_none_when_generation_fails() -> None:
    reply = asyncio.run(
        respond(
            f"{TRIGGER_KEYWORD}?",
            [],
            chat_id=123,
            recorder=make_search_recorder(),
            openrouter_api_key=OPENROUTER_API_KEY,
        )
    )

    assert reply is None


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


def test_search_chat_history_drops_unexpected_chat_hits() -> None:
    client = CrossChatOpenSearchSearchClient()

    result = asyncio.run(
        search_chat_history(client, "tg-messages", chat_id=123, query="deploy", limit=3)
    )

    assert result == "[2026-05-05T12:00:00+00:00] person: current chat deploy notes"


def make_context(
    recorder: CapturingRecorder,
    *,
    buffer: InMemoryChatBuffer | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "chat_deps": ChatDeps(
                    recorder,
                    buffer or InMemoryChatBuffer(),
                    TRIGGER_KEYWORD,
                    OPENROUTER_API_KEY,
                )
            },
        )
    )


def make_search_recorder() -> SimpleNamespace:
    return SimpleNamespace(
        client=CapturingOpenSearchSearchClient(),
        index="tg-messages",
        embed_query=FakeEmbeddings().aembed_query,
    )


class CapturingOpenRouterClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.posts = []

    def factory(self, **kwargs) -> "CapturingOpenRouterClient":
        self.kwargs = kwargs
        return self

    async def __aenter__(self) -> "CapturingOpenRouterClient":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        pass

    async def post(self, url: str, *, headers: dict, json: dict, **kwargs) -> SimpleNamespace:
        self.posts.append(
            {"url": url, "headers": headers, "json": deepcopy(json), "kwargs": kwargs}
        )
        payload = self.responses.pop(0)

        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: payload,
        )


class CapturingAgent:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.kwargs = {}
        self.inputs = {}
        self.config = {}

    def factory(self, **kwargs) -> "CapturingAgent":
        self.kwargs = kwargs
        return self

    async def ainvoke(self, inputs: dict, *, config: dict) -> dict:
        self.inputs = inputs
        self.config = config
        return {"messages": [AIMessage(content=self.reply)]}


class CapturingOpenSearchClient:
    def __init__(self, *, index_exists: bool = True) -> None:
        self.records = []
        self.created_indices = []
        self.updated_settings = []
        self.updated_mappings = []
        self.indices = CapturingOpenSearchIndices(self, index_exists=index_exists)

    async def index(self, *, index: str, id: str, body: dict) -> None:
        self.records.append({"index": index, "id": id, "body": body})


class CapturingOpenSearchIndices:
    def __init__(self, client: CapturingOpenSearchClient, *, index_exists: bool) -> None:
        self.client = client
        self.index_exists = index_exists

    async def exists(self, *, index: str) -> bool:
        return self.index_exists

    async def create(self, *, index: str, body: dict) -> None:
        self.client.created_indices.append({"index": index, "body": body})

    async def put_settings(self, *, index: str, body: dict) -> None:
        self.client.updated_settings.append({"index": index, "body": body})

    async def put_mapping(self, *, index: str, body: dict) -> None:
        self.client.updated_mappings.append({"index": index, "body": body})


class FakeEmbeddings:
    async def aembed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class CapturingOpenSearchSearchClient:
    def __init__(self) -> None:
        self.searches = []

    async def search(self, *, index: str, body: dict) -> dict:
        self.searches.append({"index": index, "body": body})
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "tg:123:789",
                        "_score": 1.0,
                        "_source": {
                            "chat_id": 123,
                            "username": "person",
                            "text": "deploy notes",
                            "timestamp": "2026-05-05T12:00:00+00:00",
                        },
                    }
                ]
            }
        }


class CrossChatOpenSearchSearchClient:
    async def search(self, *, index: str, body: dict) -> dict:
        return {
            "hits": {
                "hits": [
                    {
                        "_id": "tg:999:1",
                        "_score": 100.0,
                        "_source": {
                            "chat_id": 999,
                            "username": "other",
                            "text": "other chat private deploy notes",
                            "timestamp": "2026-05-05T12:01:00+00:00",
                        },
                    },
                    {
                        "_id": "tg:123:1",
                        "_score": 1.0,
                        "_source": {
                            "chat_id": 123,
                            "username": "person",
                            "text": "current chat deploy notes",
                            "timestamp": "2026-05-05T12:00:00+00:00",
                        },
                    },
                ]
            }
        }


class FailingOpenSearchSearchClient:
    async def search(self, *, index: str, body: dict) -> dict:
        raise RuntimeError("search failed")


class LongOpenSearchSearchClient:
    async def search(self, *, index: str, body: dict) -> dict:
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "chat_id": 123,
                            "username": "person",
                            "text": "x" * (MAX_TOOL_RESULT_CHARS + 100),
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
