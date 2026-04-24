.PHONY: bootstrap test test-one lint format serve generate

bootstrap:
	uv sync --all-extras

test:
	uv run pytest

test-one:
	uv run pytest $(TEST)

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .

serve:
	uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

generate:
	uv run python -m src.main --samples 10
