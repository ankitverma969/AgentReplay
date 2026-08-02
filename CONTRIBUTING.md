# Contributing to AgentReplay

Thank you for helping build AgentReplay.

AgentReplay is designed as a small, typed, framework-agnostic Python library.
Changes should preserve clean package boundaries and keep the core independent
from framework-specific dependencies.

## Development Setup

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pre-commit install
```

## Quality Checks

Run all checks before opening a pull request:

```bash
make check
```

This runs formatting checks, linting, type checking, and tests.

## Pull Request Guidelines

- Use short-lived feature branches from `main`.
- Include tests for behavior changes.
- Update documentation for public API changes.
- Keep dependencies minimal and justified.
- Do not add telemetry.
- Do not include real secrets in examples, fixtures, or traces.
- Keep framework-specific code inside adapter boundaries.

## Branch Naming

- `feature/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`
- `release/vX.Y.Z`

## Code Style

- Python 3.11+
- Strong typing
- Ruff formatting and linting
- MyPy strict mode
- Absolute imports within the package
- Docstrings for public modules, classes, and functions

## Security Reports

Please do not open public issues for sensitive security reports. Use private
maintainer contact channels once they are published for the project.
