import asyncio
import json
from pathlib import Path

from tgbot.evals import chat_reply


def test_score_case_requires_expected_tools() -> None:
    case = chat_reply.EvalCase(
        id="history_lookup",
        input="bot what did we decide about deploy?",
        recent_messages=[],
        expected_tools=["search_chat_history"],
        rubric="Search before answering.",
    )

    failures = chat_reply.score_case(case, "We deploy after lunch.", [])

    assert failures == ["expected tools ['search_chat_history'], got []"]


def test_score_case_checks_russian_reply_language() -> None:
    case = chat_reply.EvalCase(
        id="russian_recent_context_only",
        input="бот кратко повтори что я сказал",
        recent_messages=[],
        expected_tools=[],
        rubric="Reply in Russian.",
    )

    failures = chat_reply.score_case(case, "You said deploy after lunch.", [])

    assert "expected Russian reply for Russian input" in failures


def test_score_case_accepts_russian_reply() -> None:
    case = chat_reply.EvalCase(
        id="russian_recent_context_only",
        input="бот кратко повтори что я сказал",
        recent_messages=[],
        expected_tools=[],
        rubric="Reply in Russian.",
    )

    assert chat_reply.score_case(case, "Ты сказал: деплой после обеда.", []) == []


def test_score_case_allows_english_reply_with_russian_quote() -> None:
    case = chat_reply.EvalCase(
        id="multilingual_history_lookup",
        input="bot find the older message using the language of my request",
        recent_messages=[],
        expected_tools=["search_chat_history"],
        rubric="Reply in the request language.",
    )

    failures = chat_reply.score_case(
        case,
        'The older message is "старое сообщение: деплой после обеда".',
        ["search_chat_history"],
    )

    assert failures == []


def test_score_case_checks_random_number_range() -> None:
    case = chat_reply.EvalCase(
        id="random_number",
        input="bot pick a random number from 1 to 10",
        recent_messages=[],
        expected_tools=["random_number"],
        rubric="Use the random tool.",
    )

    failures = chat_reply.score_case(case, "42", ["random_number"])

    assert failures == ["reply does not contain an integer from 1 to 10"]


def test_load_cases_rejects_unknown_tool(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "bad_tool",
                "input": "bot do it",
                "recent_messages": [],
                "expected_tools": ["missing_tool"],
                "rubric": "No unknown tools.",
            }
        )
    )

    try:
        chat_reply.load_cases(path)
    except ValueError as error:
        assert "unknown expected tools" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_make_messages_splits_author_and_body() -> None:
    messages = chat_reply.make_messages(["alex: hello", "привет без автора"])

    assert messages[0].from_user.username == "alex"
    assert messages[0].text == "hello"
    assert messages[1].from_user.username == "person"
    assert messages[1].text == "привет без автора"


def test_run_case_captures_tool_calls(monkeypatch) -> None:
    async def fake_generate_reply(*args, on_tool_call, **kwargs) -> str:
        on_tool_call("search_chat_history", {"query": "deploy"})
        return "Found deploy notes."

    monkeypatch.setattr(chat_reply, "generate_reply", fake_generate_reply)
    case = chat_reply.EvalCase(
        id="history_lookup",
        input="bot what did we decide about deploy?",
        recent_messages=["person: bot what did we decide about deploy?"],
        expected_tools=["search_chat_history"],
        rubric="Search first.",
    )

    result = asyncio.run(chat_reply.run_case(case, openrouter_api_key="key"))

    assert result.passed
    assert result.actual_tools == ["search_chat_history"]
