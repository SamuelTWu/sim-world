import textwrap

import pygame

from .server.client import CLOSED, FAILED, GENERATING, READY, Client
from .server.local import SERVER_EXITED, SERVER_FAILED, SERVER_READY, LocalServer

from .rendering.renderer import Renderer


class Game:
    def __init__(self, seed=None):
        self.running = True
        self.seed = seed
        self.renderer = Renderer(width=1512, height=982)
        self.local_server = None
        self.client = None
        self.font = None

    def start_new_game(self, seed=None):
        self.shutdown()
        self.seed = seed if seed is not None else self.seed
        self.local_server = LocalServer(seed=self.seed)
        self.local_server.start()

    def shutdown(self):
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.local_server is not None:
            self.local_server.stop()
            self.local_server = None

    def connection_status(self):
        server, client = self.local_server, self.client
        if server.state in (SERVER_FAILED, SERVER_EXITED):
            return f"Server problem: {server.error}"
        if client is None:
            if server.state != SERVER_READY:
                return "Starting server..."
            self.client = Client(server.url, name="player")
            self.client.start()
            return "Connecting..."
        if client.state in (FAILED, CLOSED):
            return f"Disconnected: {client.error}"
        if client.state == READY:
            return None
        return "Generating world..." if client.state == GENERATING else "Connecting..."

    def draw_status(self, text):
        surface = pygame.display.get_surface()
        if self.font is None:
            pygame.font.init()
            self.font = pygame.font.Font(None, 32)
        surface.fill((20, 22, 28))
        lines = textwrap.wrap(text, 100)
        top = surface.get_height() // 2 - len(lines) * 18
        for index, line in enumerate(lines):
            image = self.font.render(line, True, (230, 230, 230))
            surface.blit(image, (surface.get_width() // 2 - image.get_width() // 2, top + index * 36))
        pygame.display.flip()

    def run(self):
        self.start_new_game()
        try:
            while self.running:
                delta_time = self.renderer.tick(60)
                self.running = self.renderer.handle_events()
                if not self.running:
                    break
                if self.renderer.restart_requested:
                    self.renderer.restart_requested = False
                    self.start_new_game()
                status = self.connection_status()
                if status is not None:
                    self.draw_status(status)
                    continue
                self.client.poll()
                self.renderer.update(delta_time)
                self.renderer.render(self.client.world, self.client.generator.maps, self.client.generator.features, [])
        finally:
            self.shutdown()
            self.renderer.close()