RUNNING, DONE, FAILED = "running", "done", "failed"


class Task:
    name = "task"

    def __init__(self, **data):
        self.data = data
        self.elapsed = 0.0

    def tick(self, entity, context, delta_time):
        self.elapsed += delta_time
        return self.step(entity, context, delta_time)

    def step(self, entity, context, delta_time):
        return DONE

    def cancel(self, entity, context):
        pass