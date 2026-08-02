# Release Engineering

AgentReplay release readiness is enforced through GitHub Actions.

## CI Matrix

CI runs on:

- Linux
- macOS
- Windows
- Python 3.11
- Python 3.12
- Python 3.13

## Quality Gates

- Ruff linting
- Ruff formatting
- MyPy strict typing
- Pytest for deterministic tests
- Coverage
- Pre-commit hooks
- Vulture dead-code detection
- Build verification
- Twine metadata check
- Benchmark smoke reports

## Security Gates

- Bandit static analysis
- pip-audit dependency vulnerability scan
- AgentReplay secret scan
- CodeQL

## Dependency Policy

The default install has no runtime third-party dependencies. Optional
capabilities are exposed through extras:

- `agentreplay[debugger]` for the Textual debugger UI
- `agentreplay[openai-agents]` for the OpenAI Agents SDK adapter
- `agentreplay[langgraph]` for the LangGraph adapter
- `agentreplay[otel]` for OTLP observability exporters
- `agentreplay[docs]` for documentation builds
- `agentreplay[security]` for standalone security audit tooling

New dependencies should be optional unless they are required by the
framework-agnostic core.

## Package Quality

The package workflow builds both wheel and source distribution artifacts, then
validates metadata with Twine. Release artifacts must include the MIT license,
typed package marker, README metadata, supported Python classifiers, and the
`agentreplay` console script.

## Benchmarks

The benchmark workflow produces a JSON report for recorder, storage, replay,
diff, profiler, debugger session, security, OpenTelemetry mapping, and
regression workloads. Timing-sensitive pytest cases are marked `performance`
and are kept separate from coverage and deterministic CI gates. Benchmark output
is an artifact for trend review and is not committed to the repository.

## Release Automation

Releases are tag-driven with:

- Wheel and source distribution builds
- Twine validation
- PyPI trusted publishing
- GitHub release assets
- Semantic release workflow for version and changelog automation

## Local Release Check

```bash
make check
make coverage
make security
make dead-code
make docs
make benchmark
make build
python -m twine check dist/*
```
