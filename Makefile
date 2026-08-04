.PHONY: check lint type test

check: lint type test  ## all local checks (CI runs these + compose validation)

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy

test:
	uv run pytest
