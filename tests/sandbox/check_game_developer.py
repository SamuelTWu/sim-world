import sys
from types import SimpleNamespace

from src.simworld.client import game as game_module
from src.simworld.client.game import Game
from src.simworld.client.menu import DEVELOPER, JOIN, QUIT, SINGLEPLAYER

failures = []


def check(condition, text):
    if not condition:
        failures.append(text)
        print("FAIL", text)


class FakeServer:
    created = []

    def __init__(self, seed=None, sandbox=False, **options):
        self.seed, self.sandbox, self.options = seed, sandbox, options
        self.started = self.stopped = False
        self.state = "starting"
        self.error = None
        FakeServer.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append(name)


def make_game(script):
    game = Game.__new__(Game)
    game.running, game.seed, game.mode, game.url = True, None, None, None
    game.local_server = game.client = None
    game.sent, game.view_sent = {}, None
    gui = Recorder()
    game.renderer = SimpleNamespace(gui=gui, place_requests=[], selection=Recorder(), hints=Recorder())
    shown = []

    def show(notice=None, screen="main"):
        shown.append((notice, screen))
        return script.pop(0)

    game.menu = SimpleNamespace(show=show)
    game.shown = shown
    return game


game_module.LocalServer = FakeServer

game = make_game([(DEVELOPER, None)])
game.open_menu()
server = game.local_server
check(game.mode == DEVELOPER, "mode is DEVELOPER")
check(server is not None and server.sandbox and server.started, "developer starts a sandbox LocalServer")

game.start_new_game()
check(server.stopped, "new game stops the old sandbox")
check(game.local_server is not server and game.local_server.sandbox and game.local_server.started, "new game starts a fresh sandbox")

failed = game.local_server
failed.state, failed.error = game_module.SERVER_FAILED, "sandbox boom"
game.menu.show = lambda notice=None, screen="main": (game.shown.append((notice, screen)), (DEVELOPER, None))[1]
game.back_to_menu()
check(game.shown[-1] == ("sandbox boom", "main"), f"failed sandbox shows its error on the main screen, got {game.shown[-1]}")
check(failed.stopped, "failed sandbox is stopped")
check(game.local_server is not failed and game.local_server.sandbox, "choosing Developer again after quitting works")

game = make_game([(SINGLEPLAYER, None)])
game.open_menu()
check(game.mode == SINGLEPLAYER and not game.local_server.sandbox, "singleplayer is not a sandbox")
game.start_new_game()
check(not game.local_server.sandbox, "singleplayer new game is not a sandbox")

game = make_game([(QUIT, None)])
game.open_menu()
check(game.running is False and game.local_server is None, "quit still quits")

if failures:
    print(f"{len(failures)} failure(s)")
    sys.exit(1)
print("OK")