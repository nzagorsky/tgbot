run:
	uv run python -m tgbot

test:
	uv run pytest

lint:
	uv run ruff check --fix .
	uv run ruff format .
