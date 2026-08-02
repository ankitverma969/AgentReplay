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

Release-impacting changes should also run the extended suite:

```bash
make test-performance
make coverage
make security
make dead-code
make docs
make benchmark
make build
python -m twine check dist/*
```

## Pull Request Guidelines

- Use short-lived feature branches from `main`.
- Include tests for behavior changes.
- Update documentation for public API changes.
- Keep dependencies minimal and justified.
- Do not add telemetry.
- Do not include real secrets in examples, fixtures, or traces.
- Keep framework-specific code inside adapter boundaries.
- Keep user-facing APIs backward compatible unless the change is explicitly
  planned for a SemVer major release.
- Prefer optional extras for integration dependencies.
- Keep generated benchmark reports, coverage reports, and build artifacts out
  of commits.

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
- No placeholder code, debug prints, or intentionally failing tests

## Release Engineering

Releases are cut from `main` after CI, docs, security, package validation, and
benchmarks pass. Version numbers follow Semantic Versioning. Changelog entries
should describe user-visible behavior, compatibility notes, and migration
guidance when applicable.

## Security Reports

Please do not open public issues for sensitive security reports. Follow
`SECURITY.md` for private disclosure guidance.
