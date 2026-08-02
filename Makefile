.PHONY: install install-dev format lint typecheck test test-performance coverage security dead-code docs benchmark check build clean

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

format:
	python -m ruff format

lint:
	python -m ruff check

typecheck:
	python -m mypy

test:
	python -m pytest -m "not performance"

test-performance:
	python -m pytest -m performance

coverage:
	python -m pytest -m "not performance" --cov=agentreplay --cov-report=term --cov-report=xml

security:
	python -m bandit -c pyproject.toml -r agentreplay
	python -m pip_audit . --skip-editable
	python -m agentreplay security scan pyproject.toml --json

dead-code:
	python -m vulture agentreplay tests benchmarks vulture_allowlist.py --min-confidence 90

docs:
	python -m mkdocs build --strict

benchmark:
	python benchmarks/benchmark_modules.py --events 1000 --json benchmark-report.json

check: lint typecheck test

build:
	python -m build

clean:
	python -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('build', 'dist', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov')]"
