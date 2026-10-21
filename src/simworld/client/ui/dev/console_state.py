from collections import namedtuple

from ....shared.dev_commands import DEV_COMMANDS, DevSyntaxError, names, parse

MAX_HISTORY = 50
MAX_LOG = 100
MAX_BUFFER = 200
MAX_LINE = 300
MAX_OPTIONS = 12
SHOW_LINES = 8
SHOW_SECONDS = 6.0
FADE_SECONDS = 1.0
NEEDS_SLASH = "dev commands start with /"

LogLine = namedtuple("LogLine", "text kind time")
Completion = namedtuple("Completion", "text options")


def clean_names(values):
    return [value for value in values if isinstance(value, str)] if isinstance(values, (list, tuple)) else []


def sources(kind, catalog):
    if kind == "command":
        return names()

    if not isinstance(catalog, dict):
        return []

    if kind == "tile":
        return clean_names(catalog.get("tiles"))

    if kind == "blueprint":
        items = clean_names(catalog.get("items", catalog.get("resources")))
        structures = clean_names(catalog.get("structures", catalog.get("resources")))
        return clean_names(catalog.get("blueprints")) + [f"item:{name}" for name in items] + [f"structure:{name}" for name in structures]

    return []


def common_prefix(values):
    first = values[0]
    length = len(first)

    for value in values[1:]:
        length = min(length, len(value))

        while length and first[:length].lower() != value[:length].lower():
            length -= 1

    return first[:length]


def complete(buffer, catalog):
    stripped = buffer.lstrip()
    lead = buffer[: len(buffer) - len(stripped)]
    slash = "/" if stripped.startswith("/") else ""
    body = stripped[1:] if slash else stripped
    parts = body.split()
    trailing = body.endswith(" ")
    index = len(parts) if trailing or not parts else len(parts) - 1
    current = "" if trailing or not parts else parts[-1]
    before = parts[:index]
    unchanged = Completion(buffer, [])

    if index == 0:
        candidates = [name for name in names() if name.startswith(current.lower())]
        more_words = lambda name: bool(DEV_COMMANDS[name].args)
    else:
        command = DEV_COMMANDS.get(before[0].lower())

        if command is None:
            return unchanged

        slots = []

        for arg in command.args:
            slots += [None, None] if arg.kind == "point" else [arg]

        slot = slots[index - 1] if index - 1 < len(slots) else None

        if slot is None or slot.complete is None:
            return unchanged

        candidates = sorted({name for name in sources(slot.complete, catalog) if name.lower().startswith(current.lower())})
        has_more = index - 1 < len(slots) - 1
        more_words = lambda name: has_more

    candidates = sorted(set(candidates))

    if not candidates:
        return unchanged

    prefix = lead + slash + "".join(f"{word} " for word in before)

    if len(candidates) == 1:
        name = candidates[0]
        return Completion(prefix + name + (" " if more_words(name) else ""), [])

    common = common_prefix(candidates)
    return Completion(prefix + common if len(common) > len(current) else buffer, candidates)


def line_alpha(age):
    if age < 0 or age >= SHOW_SECONDS:
        return 0

    if age <= SHOW_SECONDS - FADE_SECONDS:
        return 255

    return max(0, min(255, int(255 * (SHOW_SECONDS - age) / FADE_SECONDS)))


class ConsoleState:
    def __init__(self):
        self.buffer = ""
        self.cursor = 0
        self.history = []
        self.history_index = None
        self.draft = ""
        self.log = []
        self.catalog = None

    def set_text(self, text):
        self.buffer = text[:MAX_BUFFER]
        self.cursor = len(self.buffer)

    def clear(self):
        self.buffer = ""
        self.cursor = 0
        self.history_index = None
        self.draft = ""

    def edited(self):
        self.history_index = None

    def insert(self, text):
        text = "".join(char for char in str(text) if char.isprintable())[: max(0, MAX_BUFFER - len(self.buffer))]

        if not text:
            return

        self.buffer = self.buffer[: self.cursor] + text + self.buffer[self.cursor :]
        self.cursor += len(text)
        self.edited()

    def backspace(self):
        if self.cursor > 0:
            self.buffer = self.buffer[: self.cursor - 1] + self.buffer[self.cursor :]
            self.cursor -= 1
            self.edited()

    def delete(self):
        if self.cursor < len(self.buffer):
            self.buffer = self.buffer[: self.cursor] + self.buffer[self.cursor + 1 :]
            self.edited()

    def left(self):
        self.cursor = max(0, self.cursor - 1)

    def right(self):
        self.cursor = min(len(self.buffer), self.cursor + 1)

    def home(self):
        self.cursor = 0

    def end(self):
        self.cursor = len(self.buffer)

    def push_history(self, text):
        text = text.strip()

        if not text or (self.history and self.history[-1] == text):
            return

        self.history.append(text)
        del self.history[:-MAX_HISTORY]

    def history_up(self):
        if not self.history:
            return

        if self.history_index is None:
            self.draft = self.buffer
            self.history_index = len(self.history) - 1
        else:
            self.history_index = max(0, self.history_index - 1)

        self.set_text(self.history[self.history_index])

    def history_down(self):
        if self.history_index is None:
            return

        if self.history_index >= len(self.history) - 1:
            self.history_index = None
            self.set_text(self.draft)
        else:
            self.history_index += 1
            self.set_text(self.history[self.history_index])

    def set_catalog(self, data):
        self.catalog = data if isinstance(data, dict) else None

    def tab(self, now):
        result = complete(self.buffer, self.catalog)

        if result.text != self.buffer:
            self.set_text(result.text)
            self.edited()

        if len(result.options) > 1:
            shown = result.options[:MAX_OPTIONS]
            self.log_line("  ".join(shown) + (f"  (+{len(result.options) - len(shown)} more)" if len(result.options) > len(shown) else ""), "hint", now)

        return result

    def log_line(self, text, kind, now):
        self.log.append(LogLine(str(text)[:MAX_LINE], kind, now))
        del self.log[:-MAX_LOG]

    def add_result(self, text, ok, now):
        lines = str(text).split("\n") if text else ["done" if ok else "failed"]

        for line in lines:
            self.log_line(line, "ok" if ok else "error", now)

    def recent(self, now):
        return [line for line in self.log[-SHOW_LINES:] if 0 <= now - line.time < SHOW_SECONDS]

    def submit(self, context, now):
        text = self.buffer.strip()
        self.push_history(text)
        self.clear()

        if not text:
            return None

        self.log_line(f"> {text}", "echo", now)

        if not text.startswith("/"):
            self.log_line(NEEDS_SLASH, "error", now)
            return None

        try:
            return parse(text, context)
        except DevSyntaxError as problem:
            self.log_line(str(problem), "error", now)
            return None