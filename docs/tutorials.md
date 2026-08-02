# Tutorials

## Record and Save a Run

```python
from agentreplay import Recorder, SQLiteStorage

with Recorder(name="demo") as recorder:
    recorder.user_prompt("Hello")
    recorder.assistant_response("Hi")

with SQLiteStorage(".agentreplay/agentreplay.sqlite") as storage:
    recorder.save_to_storage(storage)
```

## Replay a Run

```python
from agentreplay import ReplayEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
engine = ReplayEngine(storage=storage)
session = engine.load("run-id")
print(session.timeline.render())
```

## Compare Runs

```python
from agentreplay import DiffEngine

result = DiffEngine().compare("baseline-run", "target-run")
print(result.summary())
```

## Detect a Regression

```python
from agentreplay import RegressionEngine

report = RegressionEngine().compare("baseline-run", "target-run")
print(report.summary())
```
