import os

WORD = "dev"
TIMEOUT = 2.0
MAX_BUFFER = 8


def secret_typed(buffer, word=WORD):
    return buffer.lower().endswith(word)


def dev_enabled(environ=None):
    return (os.environ if environ is None else environ).get("SIMWORLD_DEV") == "1"


class SecretBuffer:
    def __init__(self, word=WORD, timeout=TIMEOUT):
        self.word = word
        self.timeout = timeout
        self.buffer = ""
        self.last = None
        self.revealed = False

    def feed(self, text, now):
        if not text:
            return False

        if self.last is not None and now - self.last > self.timeout:
            self.buffer = ""

        self.last = now
        self.buffer = (self.buffer + text.lower())[-MAX_BUFFER:]

        if self.revealed or not secret_typed(self.buffer, self.word):
            return False

        self.revealed = True
        return True