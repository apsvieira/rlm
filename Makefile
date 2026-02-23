.PHONY: all test test-unit test-integration lint

all: lint test

test:
	uv run pytest

test-unit:
	uv run pytest --ignore=tests/test_integration.py

test-integration:
	uv run pytest tests/test_integration.py

lint:
	uv run ruff check rlm/ tests/
