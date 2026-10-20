import textwrap
import time

import pygame

from src.simworld.shared import protocol as proto
from src.simworld.client.net.connection import CLOSED, FAILED, GENERATING, READY, Client
from src.simworld.server.local import SERVER_EXITED, SERVER_FAILED, SERVER_READY, LocalServer

from .menu import JOIN, QUIT, SINGLEPLAYER, DEVELOPER, Menu
from src.simworld.client.render.renderer import Renderer


class Game:
    def __init__(self, seed=None):
        self.running = True
        self.seed = seed
        self.mode = None
        self.url = None
        self.renderer = Renderer(width=1800, height=1000)
        self.menu = Menu()
        self.local_server = None
        self.client = None
        self.font = None
        self.small_font = None
        self.sent = {}
        self.view_sent = None
        self.view_time = 0.0

    def open_menu(self, notice=None, screen="main"):
        self.shutdown()
        action, value = self.menu.show(notice, screen)
        if action == QUIT:
            self.running = False
        elif action == JOIN:
            self.start_join(value)
        elif action == DEVELOPER:
            self.start_developer()
        else:
            self.start_single_player()

    def back_to_menu(self):
        server, client = self.local_server, self.client
        notice = None
        if client is not None and client.state in (FAILED, CLOSED):
            notice = client.error
        elif server is not None and server.state in (SERVER_FAILED, SERVER_EXITED):
            notice = server.error
        self.open_menu(notice, "join" if self.mode == JOIN else "main")

    def start_single_player(self, seed=None):
        self.shutdown()
        self.mode = SINGLEPLAYER
        self.seed = seed if seed is not None else self.seed
        self.local_server = LocalServer(seed=self.seed)
        self.local_server.start()

    def start_developer(self):
        self.shutdown()
        self.mode = DEVELOPER
        self.renderer.set_dev_mode(True)
        self.local_server = LocalServer(sandbox=True)
        self.local_server.start()

    def start_join(self, url):
        self.shutdown()
        self.mode = JOIN
        self.url = url
        self.client = Client(url, name="player")
        self.view_sent = None
        self.client.start()

    def start_new_game(self, seed=None):
        if self.mode == JOIN:
            self.start_join(self.url)
        elif self.mode == DEVELOPER:
            self.start_developer()
        else:
            self.start_single_player(seed)

    def shutdown(self):
        self.renderer.set_dev_mode(False)
        self.renderer.gui.reset()
        self.renderer.place_requests.clear()
        self.renderer.selection.reset()
        self.renderer.hints.clear()
        self.sent.clear()
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.local_server is not None:
            self.local_server.stop()
            self.local_server = None

    VIEW_INTERVAL = 0.2
    VIEW_STEP = 32.0

    def send_view(self):
        """Tell the server what the camera shows (so it sends pixels in view), when it changed by a tile or more, at most 5 times a second."""
        now = time.monotonic()

        if now - self.view_time < self.VIEW_INTERVAL:
            return

        x0, y0 = self.renderer.screen_to_world((0, 0))
        x1, y1 = self.renderer.screen_to_world((self.renderer.width, self.renderer.height))
        rect = [round(x0), round(y0), round(x1), round(y1)]
        last = self.view_sent

        if last is None or any(abs(a - b) >= self.VIEW_STEP for a, b in zip(rect, last)):
            if self.client.send_view(rect):
                self.view_sent, self.view_time = rect, now

    def send_places(self):
        for blueprint_id, x, y in self.renderer.take_place_requests():
            seq = self.client.command("place", {"blueprint": blueprint_id, "position": [x, y]})

            if seq is None:
                self.renderer.gui.notify("Could not send: the connection is not usable")
            else:
                self.sent[seq] = "place"
                self.renderer.hints.add(seq, "place", (x, y), key=blueprint_id)

    def send_inspects(self):
        for pixel_id in self.renderer.take_inspect_requests():
            seq = self.client.command("inspect", {"id": pixel_id})

            if seq is not None:
                self.sent[seq] = "inspect"

    def send_edits(self):
        for pixel_id, changes in self.renderer.take_edit_requests():
            seq = self.client.command("edit_property", {"id": pixel_id, "set": changes})

            if seq is None:
                self.renderer.gui.edit_failed("Could not send: the connection is not usable")
            else:
                self.sent[seq] = "edit_property"

    def send_saves(self):
        for name, definition in self.renderer.take_save_requests():
            if self.mode == DEVELOPER:
                self.renderer.gui.save_failed("Saving is off in developer mode")
                continue
            
            seq = self.client.command("save_blueprint", {"name": name, "definition": definition})

            if seq is None:
                self.renderer.gui.save_failed("Could not send: the connection is not usable")
            else:
                self.sent[seq] = "save_blueprint"

    def send_acts(self):
        for args in self.renderer.take_act_requests():
            seq = self.client.command("act", args)

            if seq is None:
                self.renderer.gui.notify("Could not send: the connection is not usable")
            else:
                self.sent[seq] = args.get("action", "order")
                self.renderer.hints.add(seq, "order", args["point"], label=args.get("action") or "order")

    def command_accepted(self, message):
        """The server accepted a command: confirm the hint, say what was skipped, and finish a blueprint save."""
        what = self.sent.pop(message["seq"], None)
        self.renderer.hints.result(message["seq"], True)
        skipped = message.get("ignored", [])

        if what == "save_blueprint":
            self.renderer.gui.save_acknowledged()
        elif skipped:
            reasons = sorted({reason for _, reason in skipped})
            self.renderer.gui.notify(f"{len(message.get('applied', []))} ordered, {len(skipped)} skipped: {', '.join(reasons)}")

    def show_errors(self, messages):
        for message in messages:
            if message["type"] == proto.ENTITY_INFO:
                self.sent.pop(message.get("seq"), None)
                self.renderer.gui.show_pixel(message["info"])
                continue

            if message["type"] == proto.COMMAND_RESULT:
                self.command_accepted(message)
                continue

            if message["type"] == proto.ORDER_FAILED:
                self.renderer.gui.notify(f"Pixel #{message['id']} could not {message['kind']}: {message['reason']}")
                continue

            if message["type"] == proto.ERROR:
                what = self.sent.pop(message.get("seq"), None)
                self.renderer.hints.result(message.get("seq"), False)

                if what == "save_blueprint":
                    self.renderer.gui.save_failed(message["message"])
                    continue

                if what == "edit_property":
                    self.renderer.gui.edit_failed(message["message"])
                    continue

                self.renderer.gui.notify(f"Could not {what}: {message['message']}" if what else message["message"])

        if len(self.sent) > 64:
            self.sent.clear()

    def connection_status(self):
        server, client = self.local_server, self.client
        if server is not None and server.state in (SERVER_FAILED, SERVER_EXITED):
            return f"Server problem: {server.error}"
        if client is None:
            if server.state != SERVER_READY:
                return "Starting server..."
            self.client = Client(server.url, name="player")
            self.view_sent = None
            self.client.start()
            return "Connecting..."
        if client.state in (FAILED, CLOSED):
            return f"{'Could not join' if client.state == FAILED else 'Disconnected'}: {client.error}"
        if client.state == READY:
            return None
        return "Generating world..." if client.state == GENERATING else "Connecting..."

    def handle_loading_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.back_to_menu()
                return self.running
        return True

    def draw_status(self, text):
        surface = pygame.display.get_surface()
        if self.font is None:
            pygame.font.init()
            self.font = pygame.font.Font(None, 32)
            self.small_font = pygame.font.Font(None, 26)
        surface.fill((20, 22, 28))
        lines = textwrap.wrap(text, 100)
        top = surface.get_height() // 2 - len(lines) * 18
        for index, line in enumerate(lines):
            image = self.font.render(line, True, (230, 230, 230))
            surface.blit(image, (surface.get_width() // 2 - image.get_width() // 2, top + index * 36))
        hint = self.small_font.render("Esc: back to menu", True, (140, 145, 155))
        surface.blit(hint, (surface.get_width() // 2 - hint.get_width() // 2, surface.get_height() - 60))
        pygame.display.flip()

    def run(self):
        self.open_menu()
        try:
            while self.running:
                delta_time = self.renderer.tick(60)
                status = self.connection_status()
                if status is not None:
                    session = (self.client, self.local_server)
                    self.running = self.handle_loading_events()
                    if self.running and session == (self.client, self.local_server):
                        self.draw_status(status)
                    continue
                self.running = self.renderer.handle_events()
                if not self.running:
                    break
                if self.renderer.restart_requested:
                    self.renderer.restart_requested = False
                    self.start_new_game()
                    continue
                if self.renderer.menu_requested:
                    self.renderer.menu_requested = False
                    self.back_to_menu()
                    continue
                self.send_view()
                self.send_places()
                self.send_acts()
                self.send_saves()
                self.send_inspects()
                self.send_edits()
                self.show_errors(self.client.poll())
                self.renderer.add_transient_events(self.client.take_transient_events())
                self.renderer.update(delta_time)
                self.renderer.render(self.client.view())
        finally:
            self.shutdown()
            self.renderer.close()