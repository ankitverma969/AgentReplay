.PHONY: install install-dev format lint typecheck test check build clean

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

format:
	python -m ruff format agentreplay tests

lint:
	python -m ruff check agentreplay tests

typecheck:
	python -m mypy

test:
	python -m pytest

check: lint typecheck test

build:
	python -m build

clean:
	python -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('build', 'dist', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov')]"
