import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from loguru import logger

MAX_TOOL_RESULT_CHARS = 6000

ToolContext = Mapping[str, Any]
ToolHandler = Callable[[dict[str, Any], ToolContext], Awaitable[str]]


class ToolInputError(Exception):
    pass


@dataclass(frozen=True)
class Tool:
    schema: dict[str, Any]
    handler: ToolHandler


async def run_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    tools: Mapping[str, Tool],
    context: ToolContext,
) -> list[dict[str, Any]]:
    return await asyncio.gather(
        *[run_tool_call(tool_call, tools=tools, context=context) for tool_call in tool_calls]
    )


async def run_tool_call(
    tool_call: dict[str, Any],
    *,
    tools: Mapping[str, Tool],
    context: ToolContext,
) -> dict[str, Any]:
    name = tool_call.get("function", {}).get("name")
    tool_call_id = str(tool_call.get("id") or name or "tool-call")

    if not isinstance(name, str) or name not in tools:
        logger.warning("Ignoring unsupported tool call: {}", name)
        return tool_message(tool_call_id, name, "Tool error: unsupported tool")

    try:
        arguments = json.loads(tool_call.get("function", {}).get("arguments") or "{}")
    except json.JSONDecodeError:
        return tool_message(tool_call_id, name, "Tool error: invalid JSON arguments")

    if not isinstance(arguments, dict):
        return tool_message(tool_call_id, name, "Tool error: invalid JSON arguments")

    try:
        logger.info("Running tool {}", name)
        result = await tools[name].handler(arguments, context)
    except ToolInputError as error:
        return tool_message(tool_call_id, name, f"Tool error: {error}")
    except Exception:
        logger.exception("Tool {} failed", name)
        return tool_message(tool_call_id, name, f"Tool error: {name} failed")

    logger.info("Tool {} returned {} characters", name, len(result))
    if len(result) > MAX_TOOL_RESULT_CHARS:
        result = f"{result[:MAX_TOOL_RESULT_CHARS]}\n[truncated]"
    return tool_message(tool_call_id, name, result)


def tool_message(tool_call_id: str, name: Any, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": str(name or "unknown"),
        "content": content,
    }
