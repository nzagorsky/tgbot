run:
	uv run python -m tgbot


lint:
	uv run ruff check .

format:
	uv run ruff check --fix .
	uv run ruff format .
