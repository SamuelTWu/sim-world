from .rendering.renderer import Renderer
from .simulation import Simulation


class Game:
    """Client side: window, input, rendering. All game state lives in self.sim."""

    def __init__(self):
        self.running = True
        self.sim = Simulation()
        self.renderer = Renderer(width=1400, height=900)

    def start_new_game(self, seed=None):
        self.sim.start_new_game(seed)
        # Systems are recreated on every new game, so re-subscribe each time.
        self.sim.systems.events.on("tile_placed", self.on_tile_placed)

    def on_tile_placed(self, x, y, tile, **_):
        # Rendering concern only: force the world to be redrawn.
        self.renderer.cached_world = None

    def run(self):
        self.start_new_game()

        while self.running:
            delta_time = self.renderer.tick(60)

            self.running = self.renderer.handle_events()

            if not self.running:
                break

            if self.renderer.restart_requested:
                self.renderer.restart_requested = False
                self.start_new_game()

            self.sim.step(delta_time)
            self.renderer.update(delta_time)

            if self.sim.world is not None:
                self.renderer.render(
                    self.sim.world,
                    self.sim.generator.maps,
                    self.sim.generator.features,
                    self.sim.entity_manager.all(),
                )

        self.renderer.close()