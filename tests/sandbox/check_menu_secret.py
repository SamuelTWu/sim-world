import os
import sys

from src.simworld.client.dev_secret import MAX_BUFFER, TIMEOUT, SecretBuffer, dev_enabled, secret_typed

failures = 0


def check(name, ok, detail=""):
    global failures

    if not ok:
        failures += 1

    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))


def typed(text, start=0.0, gap=0.1):
    secret = SecretBuffer()
    result = [secret.feed(char, start + index * gap) for index, char in enumerate(text)]
    return secret, result


check("secret_typed: the word at the end of the buffer", secret_typed("dev") and secret_typed("xxdev") and secret_typed("DEV"))
check("secret_typed: not without the whole word, in order, at the end", not any(secret_typed(text) for text in ("", "d", "de", "dxev", "ved", "dev ", "dvev", "edv")))

secret, result = typed("dev")
check("d, e, v typed in order reveals it, on the v", secret.revealed and result == [False, False, True])
secret, result = typed("DEV")
check("capital letters count too", secret.revealed)
secret, result = typed("xxdev")
check("other keys before the word do not matter", secret.revealed)

for text in ("dxev", "edv", "dde", "dv", "ev", "deev", "d e v", "de", "vde", "xyz"):
    check(f"typing {text!r} does not reveal it", not typed(text)[0].revealed)

secret = SecretBuffer()
secret.feed("d", 0.0)
secret.feed("e", 0.1)
check("typing is ignored when the key has no character (arrows, shift)", secret.feed("", 0.2) is False and secret.feed("v", 0.3) is True)

secret = SecretBuffer()
secret.feed("d", 0.0)
secret.feed("e", 0.5)
check("a pause longer than the timeout starts the word again", secret.feed("v", 0.5 + TIMEOUT + 0.5) is False and not secret.revealed)

secret = SecretBuffer()
secret.feed("d", 0.0)
secret.feed("e", 1.0)
check("a pause shorter than the timeout does not", secret.feed("v", 1.0 + TIMEOUT - 0.1) is True)

secret = SecretBuffer()
secret.feed("d", 0.0)
secret.feed("e", 0.1)
secret.feed("x", 5.0)
secret.feed("d", 5.1)
secret.feed("e", 5.2)
check("after a timeout the word can be typed again from the start", secret.feed("v", 5.3) is True)

secret, _ = typed("dev")
check("once revealed it stays revealed, and does not report it again", secret.feed("d", 10.0) is False and secret.feed("e", 10.1) is False and secret.feed("v", 10.2) is False and secret.revealed)

secret = SecretBuffer()

for index in range(1000):
    secret.feed("abcdefg"[index % 7], index * 0.01)

check("the buffer stays short", len(secret.buffer) <= MAX_BUFFER)
check("a different word works for tests", SecretBuffer(word="xyz").feed("x", 0) is False)

check("SIMWORLD_DEV=1 enables it", dev_enabled({"SIMWORLD_DEV": "1"}) is True)
check("anything else does not", not any(dev_enabled(env) for env in ({}, {"SIMWORLD_DEV": "0"}, {"SIMWORLD_DEV": ""}, {"SIMWORLD_DEV": "true"}, {"SIMWORLD_DEV": "yes"})))
previous = os.environ.pop("SIMWORLD_DEV", None)
check("it reads the real environment by default", dev_enabled() is False)
os.environ["SIMWORLD_DEV"] = "1"
check("and notices the variable", dev_enabled() is True)

if previous is None:
    del os.environ["SIMWORLD_DEV"]
else:
    os.environ["SIMWORLD_DEV"] = previous

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

try:
    import pygame

    from src.simworld.client.menu import DEVELOPER, JOIN, QUIT, SINGLEPLAYER, Menu
except ImportError as problem:
    print(f"SKIP menu section (needs pygame): {problem}")
else:
    surface = pygame.Surface((1800, 1000))

    def labels(menu):
        return [label for label, _, _ in menu.buttons(surface)]

    def key(char, code=None):
        return pygame.event.Event(pygame.KEYDOWN, key=code if code is not None else (ord(char) if char else pygame.K_LSHIFT), unicode=char, mod=0)

    os.environ.pop("SIMWORLD_DEV", None)
    menu = Menu()
    check("a fresh menu has no Developer button", "Developer" not in labels(menu) and labels(menu) == ["Singleplayer", "Join", "Quit"], str(labels(menu)))
    check("it is not reachable by clicking where it would be", all(action != DEVELOPER for _, action, _ in menu.buttons(surface)))

    for char in "dev":
        menu.handle(key(char), surface)

    check("typing dev on the main screen reveals it under Singleplayer", labels(menu) == ["Singleplayer", "Developer", "Join", "Quit"], str(labels(menu)))
    check("the new button is selected", menu.selected == 1)
    check("activating it returns DEVELOPER", menu.activate(DEVELOPER) == (DEVELOPER, None))
    check("Enter on it returns DEVELOPER", menu.handle(key("", pygame.K_RETURN), surface) == (DEVELOPER, None))
    check("the other buttons still work", menu.activate(SINGLEPLAYER) == (SINGLEPLAYER, None) and menu.activate(QUIT) == (QUIT, None))
    check("a new menu object is hidden again", "Developer" not in labels(Menu()))

    menu = Menu()
    for char in "dxev":
        menu.handle(key(char), surface)

    check("other keys do not reveal it", "Developer" not in labels(menu))

    menu = Menu()
    menu.activate("join_screen")
    before = menu.address

    for char in "dev":
        menu.handle(key(char), surface)

    menu.activate("back")
    check("typing dev in the address field goes to the address, not the secret", menu.address == before + "dev" and "Developer" not in labels(menu), menu.address)

    os.environ["SIMWORLD_DEV"] = "1"
    menu = Menu()
    check("SIMWORLD_DEV=1 shows it from the start", labels(menu) == ["Singleplayer", "Developer", "Join", "Quit"], str(labels(menu)))
    del os.environ["SIMWORLD_DEV"]

print("\nALL PASSED" if not failures else f"\n{failures} FAILED")
sys.exit(1 if failures else 0)