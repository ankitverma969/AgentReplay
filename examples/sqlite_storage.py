"""SQLite storage example for AgentReplay."""

from pathlib import Path

from agentreplay import Recorder, SQLiteStorage


def main() -> None:
    """Record and persist a simple run to SQLite."""
    db_path = Path(".agentreplay") / "example.sqlite"

    with Recorder(name="storage-example") as recorder:
        recorder.user_prompt("Store this run locally.")
        recorder.assistant_response("Stored.")

    with SQLiteStorage(db_path) as storage:
        recorder.save_to_storage(storage)
        run_id = recorder.last_run_id()
        if run_id is None:
            raise RuntimeError("Recorder did not produce a run id.")
        trace = Recorder.load_from_storage(storage, run_id)

    print(f"loaded {len(trace.events)} events from {db_path}")


if __name__ == "__main__":
    main()
