import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tgbot.features.chat.responder import generate_reply
from tgbot.features.history.tool import SEARCH_CHAT_HISTORY_TOOL_NAME
from tgbot.features.random.tool import RANDOM_NUMBER_TOOL_NAME

PROJECT_ROOT = Path(__file__).parents[3]
DEFAULT_CASES_PATH = PROJECT_ROOT / "evals" / "chat_reply_cases.jsonl"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "evals" / "results"
EVAL_CHAT_ID = 9001
KNOWN_TOOLS = {SEARCH_CHAT_HISTORY_TOOL_NAME, RANDOM_NUMBER_TOOL_NAME}


@dataclass(frozen=True)
class EvalCase:
    id: str
    input: str
    recent_messages: list[str]
    expected_tools: list[str]
    rubric: str


@dataclass(frozen=True)
class EvalResult:
    id: str
    passed: bool
    reply: str | None
    expected_tools: list[str]
    actual_tools: list[str]
    failures: list[str]
    rubric: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real chat reply evals against OpenRouter.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--openrouter-api-key", default=os.environ.get("OPENROUTER_API_KEY"))
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    openrouter_api_key = args.openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        raise SystemExit("Missing OPENROUTER_API_KEY")

    results = asyncio.run(run_evals(args.cases, openrouter_api_key=openrouter_api_key))
    write_results(results, args.results_dir)
    print_summary(results)

    if any(not result.passed for result in results):
        raise SystemExit(1)


async def run_evals(cases_path: Path, *, openrouter_api_key: str) -> list[EvalResult]:
    return [await run_case(case, openrouter_api_key=openrouter_api_key) for case in load_cases(cases_path)]


async def run_case(case: EvalCase, *, openrouter_api_key: str) -> EvalResult:
    tool_calls: list[dict[str, Any]] = []

    def observe_tool_call(name: str, arguments: dict[str, Any]) -> None:
        tool_calls.append({"name": name, "arguments": arguments})

    try:
        reply = await generate_reply(
            case.input,
            make_messages(case.recent_messages),
            chat_id=EVAL_CHAT_ID,
            recorder=SimpleNamespace(client=FakeSearchClient(case.id), index="eval-messages"),
            openrouter_api_key=openrouter_api_key,
            on_tool_call=observe_tool_call,
        )
    except Exception as error:
        return EvalResult(
            id=case.id,
            passed=False,
            reply=None,
            expected_tools=case.expected_tools,
            actual_tools=[tool_call["name"] for tool_call in tool_calls],
            failures=[f"model call failed: {error.__class__.__name__}: {error}"],
            rubric=case.rubric,
        )

    actual_tools = [tool_call["name"] for tool_call in tool_calls]
    failures = score_case(case, reply, actual_tools)
    return EvalResult(
        id=case.id,
        passed=not failures,
        reply=reply,
        expected_tools=case.expected_tools,
        actual_tools=actual_tools,
        failures=failures,
        rubric=case.rubric,
    )


def score_case(case: EvalCase, reply: str | None, actual_tools: list[str]) -> list[str]:
    failures = []
    if sorted(actual_tools) != sorted(case.expected_tools):
        failures.append(
            f"expected tools {sorted(case.expected_tools)}, got {sorted(actual_tools)}"
        )

    if not reply or not reply.strip():
        failures.append("reply is empty")
        return failures

    reply_text = reply.strip()
    if first_script(case.input) == "cyrillic" and first_script(reply_text) != "cyrillic":
        failures.append("expected Russian reply for Russian input")
    if first_script(case.input) == "latin" and first_script(reply_text) == "cyrillic":
        failures.append("expected English reply for English input")
    if case.id == "random_number" and not contains_integer_between(reply_text, 1, 10):
        failures.append("reply does not contain an integer from 1 to 10")
    if case.id == "no_markdown_needed" and any(mark in reply_text for mark in ("**", "__", "#")):
        failures.append("reply uses unnecessary Markdown")
    return failures


def load_cases(path: Path) -> list[EvalCase]:
    cases = []
    seen_ids = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        case = EvalCase(
            id=required_str(raw, "id", line_number),
            input=required_str(raw, "input", line_number),
            recent_messages=required_str_list(raw, "recent_messages", line_number),
            expected_tools=required_str_list(raw, "expected_tools", line_number),
            rubric=required_str(raw, "rubric", line_number),
        )
        if case.id in seen_ids:
            raise ValueError(f"duplicate case id on line {line_number}: {case.id}")
        if unknown_tools := set(case.expected_tools) - KNOWN_TOOLS:
            raise ValueError(f"unknown expected tools on line {line_number}: {sorted(unknown_tools)}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError(f"no eval cases found in {path}")
    return cases


def required_str(raw: dict[str, Any], key: str, line_number: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"line {line_number}: {key} must be a non-empty string")
    return value


def required_str_list(raw: dict[str, Any], key: str, line_number: int) -> list[str]:
    value = raw.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"line {line_number}: {key} must be a list of strings")
    return value


def make_messages(lines: list[str]) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            chat=SimpleNamespace(id=EVAL_CHAT_ID, type="group", title="Eval Chat"),
            from_user=SimpleNamespace(id=idx + 1, username=author, first_name=author, is_bot=False),
            reply_to_message=None,
            message_id=idx + 1,
            date=datetime(2026, 5, 5, 12, idx, tzinfo=timezone.utc),
            text=body,
            caption=None,
        )
        for idx, line in enumerate(lines)
        for author, body in [split_message_line(line)]
    ]


def split_message_line(line: str) -> tuple[str, str]:
    author, separator, body = line.partition(":")
    if not separator:
        return "person", line.strip()
    return author.strip() or "person", body.strip()


class FakeSearchClient:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id

    async def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.case_id == "history_tool_failure":
            return {"hits": {"hits": []}}

        text = {
            "history_lookup": "deploy after lunch unless rollback metrics degrade",
            "multilingual_history_lookup": "старое сообщение: деплой после обеда",
            "russian_history_lookup": "Макс сказал проверить инвойсы завтра утром",
        }.get(self.case_id, "relevant older chat history")
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "username": "person",
                            "text": text,
                            "timestamp": "2026-05-05T12:00:00+00:00",
                        }
                    }
                ]
            }
        }


def write_results(results: list[EvalResult], results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"chat_reply_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with path.open("w") as file:
        for result in results:
            file.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")
    print(f"wrote results: {path}")
    return path


def print_summary(results: list[EvalResult]) -> None:
    passed = sum(result.passed for result in results)
    print(f"chat reply evals: {passed}/{len(results)} passed")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.id}: tools={result.actual_tools} reply={result.reply!r}")
        if result.failures:
            print(f"  failures: {'; '.join(result.failures)}")
            print(f"  rubric: {result.rubric}")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def first_script(text: str) -> str | None:
    for char in text:
        folded = char.casefold()
        if "a" <= folded <= "z":
            return "latin"
        if "а" <= folded <= "я" or folded == "ё":
            return "cyrillic"
    return None


def contains_integer_between(text: str, lower: int, upper: int) -> bool:
    for token in text.replace(".", " ").replace(",", " ").split():
        if token.lstrip("+-").isdigit() and lower <= int(token) <= upper:
            return True
    return False


if __name__ == "__main__":
    main()
