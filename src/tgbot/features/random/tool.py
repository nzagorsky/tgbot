import random
from typing import Any

from tgbot.llm.tools import Tool, ToolContext, ToolInputError

RANDOM_NUMBER_TOOL_NAME = "random_number"


async def run_random_number_tool(arguments: dict[str, Any], context: ToolContext) -> str:
    min_value = parse_bound(arguments.get("min", 1), "min")
    max_value = parse_bound(arguments.get("max", 100), "max")

    if min_value > max_value:
        raise ToolInputError("min cannot be greater than max")

    return str(random.randint(min_value, max_value))


def parse_bound(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer")
    return value


RANDOM_NUMBER_TOOL = Tool(
    schema={
        "type": "function",
        "function": {
            "name": RANDOM_NUMBER_TOOL_NAME,
            "description": "Generate a random integer in an inclusive range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min": {
                        "type": "integer",
                        "description": "Inclusive lower bound. Defaults to 1.",
                    },
                    "max": {
                        "type": "integer",
                        "description": "Inclusive upper bound. Defaults to 100.",
                    },
                },
            },
        },
    },
    handler=run_random_number_tool,
)
