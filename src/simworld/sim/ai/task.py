from typing import Any

RUNNING, DONE, FAILED = "running", "done", "failed"


class Task:
    name = "task"

    def __init__(self, **data):
        self.data = dict(data)
        self.elapsed = 0.0
        self.state = {}
        self.reason = ""

    def tick(self, entity, context, delta_time):
        self.elapsed += delta_time
        return self.step(entity, context, delta_time)

    def step(self, entity, context, delta_time):
        return DONE

    def cancel(self, entity, context):
        pass

    def finish(self, entity, context, status):
        pass

    def fail(self, reason: str):
        self.reason = reason
        return FAILED

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "data": self.data, "elapsed": self.elapsed, "state": self.state, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        task = cls(**dict(data.get("data", {})))
        task.elapsed = float(data.get("elapsed", 0.0))
        task.state = dict(data.get("state", {}))
        task.reason = str(data.get("reason", ""))
        return task