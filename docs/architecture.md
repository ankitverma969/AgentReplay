# AgentReplay Architecture

This document records the Phase 1 project foundation.

AgentReplay is organized around stable boundaries:

- `agentreplay.core` contains domain concepts shared by all layers.
- `agentreplay.recording` will contain event capture behavior.
- `agentreplay.storage` will contain persistence interfaces and backends.
- `agentreplay.replay` will contain replay behavior.
- `agentreplay.diff` will contain trace comparison behavior.
- `agentreplay.adapters` contains framework integration contracts.
- `agentreplay.plugins` contains external extension discovery conventions.
- `agentreplay.cli` exposes the command line interface.

Only configuration, logging, versioning, dependency injection primitives, and
CLI scaffolding are active in Phase 1.

## Design Rules

- Core modules do not import framework-specific packages.
- Framework integrations belong behind adapters.
- Optional framework dependencies are not imported from package initialization.
- Local SQLite remains the default future storage direction.
- Recording, replay, diffing, storage behavior, and first-class adapters are not
  implemented in Phase 1.
