.PHONY: install lint typecheck contract test check

install:
	python -m pip install -e ".[dev]"

lint:
	ruff check src tests
	ruff format --check src tests

typecheck:
	mypy

contract:
	lint-imports --config .importlinter

test:
	pytest -q

check: lint typecheck contract test
