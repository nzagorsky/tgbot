import random
from langchain.tools import tool

from tgbot.llm.tools import ToolInputError

RANDOM_NUMBER_TOOL_NAME = "random_number"


@tool
def run_random_number_tool(min_value: int, max_value: int) -> str:
    if min_value > max_value:
        raise ToolInputError("min cannot be greater than max")

    return str(random.randint(min_value, max_value))
