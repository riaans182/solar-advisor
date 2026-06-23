.PHONY: install lint typecheck contract test check

# Self-contained: every target uses the project venv, so no PATH juggling is
# needed. `make install` bootstraps the venv from the system python3.
VENV := .venv
BIN := $(VENV)/bin

install:
	python3 -m venv $(VENV)
	$(BIN)/python -m pip install -e ".[dev]"

lint:
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

typecheck:
	$(BIN)/mypy

contract:
	$(BIN)/lint-imports --config .importlinter

test:
	$(BIN)/pytest -q

check: lint typecheck contract test
