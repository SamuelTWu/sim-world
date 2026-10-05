from .rendering.renderer import Renderer
from .simulation import Simulation, TICK_DT

MAX_FRAME_TIME = 0.25
MAX_STEPS_PER_FRAME = 5


class Game:
    def __init__(self):
        self.running = True
        self.sim = Simulation()
        self.renderer = Renderer(width=1800, height=1000)
        self.accumulator = 0.0
        self.alpha = 0.0

    def start_new_game(self, seed=None):
        self.sim.start_new_game(seed)
        self.accumulator = 0.0
        self.sim.systems.events.on("tile_placed", self.on_tile_placed)

    def on_tile_placed(self, x, y, tile, **_):
        self.renderer.cached_world = None

    def step_simulation(self, delta_time):
        self.accumulator += min(delta_time, MAX_FRAME_TIME)
        steps = 0
        while self.accumulator >= TICK_DT and steps < MAX_STEPS_PER_FRAME:
            self.sim.step()
            self.accumulator -= TICK_DT
            steps += 1
        if self.accumulator >= TICK_DT:
            self.accumulator = 0.0
        self.alpha = self.accumulator / TICK_DT

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
            self.step_simulation(delta_time)
            self.renderer.update(delta_time)
            if self.sim.world is not None:
                self.renderer.render(self.sim.world, self.sim.generator.maps, self.sim.generator.features, self.sim.entity_manager.all())
        self.renderer.close()