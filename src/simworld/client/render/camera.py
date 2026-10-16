import pygame


class Camera:
    def __init__(self, screen_width: int, screen_height: int, tile_size: int = 32, ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.tile_size = tile_size

        self.x = 0.0
        self.y = 0.0

        self.zoom = 1.0
        self.min_zoom = 0.01
        self.max_zoom = 10.0

        self.move_speed = 500.0

        self.dragging = False
        self.last_mouse_position = None

    @property
    def scaled_tile_size(self) -> float:
        return self.tile_size * self.zoom

    def fit_world(self, world_width: int, world_height: int):
        world_pixel_width = world_width * self.tile_size
        world_pixel_height = world_height * self.tile_size

        self.x = world_pixel_width / 2
        self.y = world_pixel_height / 2

        self.zoom = min(self.screen_width / world_pixel_width, self.screen_height / world_pixel_height)
        self.zoom = max(self.min_zoom, min(self.zoom, self.max_zoom))

    def update(self, delta_time: float):
        keys = pygame.key.get_pressed()

        direction_x = 0
        direction_y = 0

        if keys[pygame.K_a]:
            direction_x -= 1
        if keys[pygame.K_d]:
            direction_x += 1
        if keys[pygame.K_w]:
            direction_y -= 1
        if keys[pygame.K_s]:
            direction_y += 1

        if direction_x != 0 or direction_y != 0:
            direction = pygame.Vector2(direction_x, direction_y).normalize()
            self.x += direction.x * self.move_speed * delta_time
            self.y += direction.y * self.move_speed * delta_time

        if self.dragging:
            mouse_position = pygame.Vector2(pygame.mouse.get_pos())

            if self.last_mouse_position is not None:
                movement = mouse_position - self.last_mouse_position
                self.x -= movement.x / self.zoom
                self.y -= movement.y / self.zoom

            self.last_mouse_position = mouse_position

    def handle_event(self, event):
        if event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                self.zoom_in()
            elif event.y < 0:
                self.zoom_out()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.dragging = True
                self.last_mouse_position = pygame.Vector2(event.pos)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.dragging = False
                self.last_mouse_position = None

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                self.zoom_in()
            elif event.key == pygame.K_MINUS:
                self.zoom_out()

    def zoom_in(self):
        self.zoom = min(self.zoom * 1.2, self.max_zoom)

    def zoom_out(self):
        self.zoom = max(self.zoom / 1.2, self.min_zoom)

    def world_to_screen(self, world_x: float, world_y: float):
        screen_x = (world_x - self.x) * self.zoom + self.screen_width / 2
        screen_y = (world_y - self.y) * self.zoom + self.screen_height / 2
        return screen_x, screen_y

    def screen_to_world(self, screen_x: float, screen_y: float):
        world_x = (screen_x - self.screen_width / 2) / self.zoom + self.x
        world_y = (screen_y - self.screen_height / 2) / self.zoom + self.y
        return world_x, world_y

    def get_visible_tile_bounds(self, world):
        world_left, world_top = self.screen_to_world(0, 0)
        world_right, world_bottom = self.screen_to_world(self.screen_width, self.screen_height)

        min_x = max(0, int(world_left // self.tile_size) - 1)
        max_x = min(world.width - 1, int(world_right // self.tile_size) + 1)
        min_y = max(0, int(world_top // self.tile_size) - 1)
        max_y = min(world.height - 1, int(world_bottom // self.tile_size) + 1)

        return min_x, max_x, min_y, max_y

    def get_hovered_tile(self, world):
        mouse_x, mouse_y = pygame.mouse.get_pos()
        world_x, world_y = self.screen_to_world(mouse_x, mouse_y)

        tile_x = int(world_x // self.tile_size)
        tile_y = int(world_y // self.tile_size)

        if tile_x < 0 or tile_x >= world.width or tile_y < 0 or tile_y >= world.height:
            return None

        return world.get_tile(tile_x, tile_y)

    def draw_hovered_tile_name(self, screen, world, font):
        tile = self.get_hovered_tile(world)

        if tile is None:
            return

        mouse_x, mouse_y = pygame.mouse.get_pos()

        text = font.render(getattr(tile, "name", "Unknown"), True, (255, 255, 255))
        background = text.get_rect(center=(mouse_x, mouse_y))
        background.inflate_ip(6, 4)

        pygame.draw.rect(screen, (0, 0, 0), background)
        screen.blit(text, text.get_rect(center=(mouse_x, mouse_y)))
