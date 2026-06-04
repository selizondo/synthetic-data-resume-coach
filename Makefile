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
	PYTHONPATH=. uv run uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

generate:
	uv run python -m src.main --num-jobs 10 --no-heatmaps
