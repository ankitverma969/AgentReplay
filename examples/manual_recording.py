"""Manual in-memory recording example for AgentReplay."""

from agentreplay import Recorder


def main() -> None:
    """Record a simple agent-like execution in memory."""
    with Recorder(name="example-agent") as recorder:
        recorder.system_prompt("Answer briefly.")
        recorder.user_prompt("What is AgentReplay?")
        recorder.llm_request(provider_name="example", model_name="demo-model")
        recorder.llm_response(
            provider_name="example",
            model_name="demo-model",
            response="A local recorder for agent execution events.",
            token_usage={"input_tokens": 8, "output_tokens": 9, "total_tokens": 17},
            latency_ms=24.0,
        )
        recorder.assistant_response("A local recorder for agent execution events.")

    trace = recorder.trace()
    print(f"recorded {len(trace.events)} events for run {trace.run.run_id}")


if __name__ == "__main__":
    main()
