"""Replay example for AgentReplay."""

from pathlib import Path

from agentreplay import Recorder, ReplayEngine, SQLiteStorage


def main() -> None:
    """Record, store, and replay a simple run."""
    db_path = Path(".agentreplay") / "replay-example.sqlite"

    with Recorder(name="replay-example") as recorder:
        recorder.user_prompt("Replay this run.")
        recorder.llm_request(provider_name="example", model_name="demo")
        recorder.llm_response(response="Replayed from local data.")
        recorder.assistant_response("Replayed from local data.")

    with SQLiteStorage(db_path) as storage:
        recorder.save_to_storage(storage)
        run_id = recorder.last_run_id()
        if run_id is None:
            raise RuntimeError("Recorder did not produce a run id.")
        engine = ReplayEngine(storage=storage)
        engine.load(run_id)
        print(engine.render_timeline())


if __name__ == "__main__":
    main()
