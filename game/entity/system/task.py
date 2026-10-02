from typing import Any

RUNNING, DONE, FAILED = "running", "done", "failed"

class Task:
    name = "task"

    def __init__(self, **data):
        self.data = dict(data)
        self.elapsed = 0.0

    def tick(self, entity, context, delta_time):
        self.elapsed += delta_time
        return self.step(entity, context, delta_time)

    def step(self, entity, context, delta_time):
        return DONE

    def cancel(self, entity, context):
        pass

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "data": self.data, "elapsed": self.elapsed}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        task = cls(**dict(data.get("data", {})))
        task.elapsed = float(data.get("elapsed", 0.0))
        return task