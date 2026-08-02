# FAQ

## Does AgentReplay call LLMs?

No. Recording observes an execution. Replay, diff, profiling, reporting, and
regression analysis use recorded data only.

## Does AgentReplay require an API key?

No. The core library runs locally without API keys.

## Why is SQLite the default storage backend?

SQLite provides a zero-service local backend that is easy to inspect, copy, and
use in CI. The storage interface supports future backends.

## Is the debugger dependency installed by default?

No. Install `agentreplay[debugger]` to use the Textual terminal debugger.

## Which Python versions are supported?

Python 3.11, 3.12, and 3.13 are tested in CI on Linux, macOS, and Windows.
