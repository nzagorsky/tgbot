import json
from pathlib import Path


EVAL_CASES = Path(__file__).parents[1] / "evals" / "chat_reply_cases.jsonl"
KNOWN_TOOLS = {"search_chat_history", "random_number"}


def test_chat_reply_eval_cases_are_valid() -> None:
    cases = [json.loads(line) for line in EVAL_CASES.read_text().splitlines()]

    assert cases
    assert len({case["id"] for case in cases}) == len(cases)
    for case in cases:
        assert isinstance(case["input"], str) and case["input"].strip()
        assert isinstance(case["recent_messages"], list)
        assert set(case["expected_tools"]) <= KNOWN_TOOLS
        assert isinstance(case["rubric"], str) and case["rubric"].strip()
