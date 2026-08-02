"""Record two local runs and compare them with the AgentReplay diff engine."""

from __future__ import annotations

import sys

from agentreplay import DiffEngine, Recorder


def main() -> None:
    """Run the diff example."""
    with Recorder(name="baseline") as baseline:
        baseline.user_prompt("Summarize AgentReplay.")
        baseline.llm_request(provider_name="example", model_name="demo-model")
        baseline.assistant_response("AgentReplay records agent executions.")

    with Recorder(name="candidate") as candidate:
        candidate.user_prompt("Summarize AgentReplay briefly.")
        candidate.llm_request(provider_name="example", model_name="demo-model")
        candidate.assistant_response("AgentReplay records and compares runs.")

    result = DiffEngine().compare(baseline.trace(), candidate.trace())
    sys.stdout.write(f"{result.summary()}\n")


if __name__ == "__main__":
    main()
