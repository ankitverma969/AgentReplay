# AgentReplay Release Process

AgentReplay releases are cut from `main` after the release-readiness checks pass.
The package follows Semantic Versioning.

## Prerequisites

- All changes merged into `main`.
- GitHub Actions CI is green on Linux, macOS, and Windows for Python 3.11, 3.12,
  and 3.13.
- Security, dead-code, documentation, benchmark, package, and release workflows
  pass.
- `CHANGELOG.md` includes user-visible changes and compatibility notes.

## Local Validation

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
make check
make coverage
make security
make dead-code
make docs
make benchmark
make build
python -m twine check dist/*
```

## Versioning

Use Conventional Commit messages so semantic-release can infer the next version:

- `fix:` for patch releases
- `feat:` for minor releases
- breaking changes for major releases

The canonical version is `project.version` in `pyproject.toml`.

## Publishing

Publishing is automated through GitHub Actions:

- `semantic-release.yml` prepares release commits and tags.
- `release.yml` builds wheel and source distribution artifacts.
- PyPI publishing uses trusted publishing through GitHub Actions OIDC.
- GitHub Releases receive the built artifacts.

Manual publishing should be reserved for incident recovery and must still use
the validated artifacts from CI.

## Post-Release Checks

- Confirm the PyPI project page renders metadata correctly.
- Install from PyPI in a fresh Python 3.11, 3.12, and 3.13 environment.
- Run `agentreplay --help`.
- Verify documentation is published and links resolve.
- Create a GitHub release note from the changelog entry.
