run:
	uv run python -m tgbot

test:
	uv run pytest

eval:
	uv run python -m tgbot.evals.chat_reply

lint:
	uv run ruff check .

format:
	uv run ruff check --fix .
	uv run ruff format .
