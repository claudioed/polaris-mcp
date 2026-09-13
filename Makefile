.PHONY: install lint format test coverage build smoke audit clean

install:
	python3 -m pip install -e '.[dev]'

lint:
	ruff check src tests scripts
	ruff format --check src tests scripts

format:
	ruff check --fix src tests scripts
	ruff format src tests scripts

test:
	pytest

coverage:
	pytest --cov=polaris_mcp --cov-report=term-missing --cov-fail-under=90

build:
	python -m build

smoke: build
	python3 -m venv .smoke-venv
	.smoke-venv/bin/pip install --quiet --upgrade pip
	.smoke-venv/bin/pip install --quiet dist/polaris_mcp-*.whl
	.smoke-venv/bin/polaris-mcp --help
	.smoke-venv/bin/python scripts/smoke_stdio.py
	rm -rf .smoke-venv

audit:
	pip-audit --skip-editable

clean:
	rm -rf dist build src/*.egg-info .smoke-venv .pytest_cache .ruff_cache .coverage
