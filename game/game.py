import textwrap

import pygame

from server.client import CLOSED, FAILED, GENERATING, READY, Client
from server.local import SERVER_EXITED, SERVER_FAILED, SERVER_READY, LocalServer

from .menu import JOIN, QUIT, SINGLEPLAYER, Menu
from ui.rendering.renderer import Renderer


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

    def open_menu(self, notice=None, screen="main"):
        self.shutdown()
        action, value = self.menu.show(notice, screen)
        if action == QUIT:
            self.running = False
        elif action == JOIN:
            self.start_join(value)
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

    def start_join(self, url):
        self.shutdown()
        self.mode = JOIN
        self.url = url
        self.client = Client(url, name="player")
        self.client.start()

    def start_new_game(self, seed=None):
        if self.mode == JOIN:
            self.start_join(self.url)
        else:
            self.start_single_player(seed)

    def shutdown(self):
        self.renderer.gui.reset()
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.local_server is not None:
            self.local_server.stop()
            self.local_server = None

    def connection_status(self):
        server, client = self.local_server, self.client
        if server is not None and server.state in (SERVER_FAILED, SERVER_EXITED):
            return f"Server problem: {server.error}"
        if client is None:
            if server.state != SERVER_READY:
                return "Starting server..."
            self.client = Client(server.url, name="player")
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
                self.client.poll()
                self.renderer.update(delta_time)
                self.renderer.render(self.client.view())
        finally:
            self.shutdown()
            self.renderer.close()