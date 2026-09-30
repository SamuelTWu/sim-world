class EventBus:
    def __init__(self):
        self.listeners = {}

    def on(self, kind, listener):
        self.listeners.setdefault(kind, []).append(listener)

    def off(self, kind, listener):
        if listener in self.listeners.get(kind, []):
            self.listeners[kind].remove(listener)

    def emit(self, kind, **data):
        for listener in list(self.listeners.get(kind, [])):
            listener(**data)