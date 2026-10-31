"""Deterministic game simulation; no terminal or agent dependencies."""

from dataclasses import dataclass
import random

DINO = ("    ####", "    #.##", "#  ###  ", "#####   ", "  # #   ")
CACTUS = (" | ", "|||", " | ")
DINO_X = 7


@dataclass
class Obstacle:
    x: float


class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.best = 0
        self.reset()

    def reset(self):
        self.distance = 0.0
        self.height = 0.0
        self.velocity = 0.0
        self.obstacles = []
        self.until_spawn = 38.0
        self.over = False

    @property
    def score(self):
        return int(self.distance)

    @property
    def speed(self):
        return min(34.0, 18.0 + self.distance / 220)

    def jump(self):
        if self.over:
            self.reset()
        if self.height == 0:
            self.velocity = 24.0

    def tick(self, seconds, width):
        # Small substeps prevent tunneling through cacti after a slow frame.
        remaining = min(max(0, seconds), 0.25)
        while remaining > 0 and not self.over:
            dt = min(remaining, 1 / 120)
            remaining -= dt
            self.velocity -= 55 * dt
            self.height = max(0.0, self.height + self.velocity * dt)
            if self.height == 0:
                self.velocity = max(0, self.velocity)
            movement = self.speed * dt
            self.distance += movement
            self.best = max(self.best, self.score)
            self.until_spawn -= movement
            if self.until_spawn <= 0:
                self.obstacles.append(Obstacle(float(width + 2)))
                self.until_spawn = self.rng.uniform(35, 55)
            for obstacle in self.obstacles:
                obstacle.x -= movement
                # Rows are measured upward from the ground; transparent cells
                # in both sprites do not count as a collision.
                dino_cells = {
                    (DINO_X + x, round(self.height) + len(DINO) - 1 - y)
                    for y, row in enumerate(DINO)
                    for x, cell in enumerate(row) if cell != " "
                }
                cactus_cells = {
                    (round(obstacle.x) + x, len(CACTUS) - 1 - y)
                    for y, row in enumerate(CACTUS)
                    for x, cell in enumerate(row) if cell != " "
                }
                if dino_cells & cactus_cells:
                    self.over = True
            self.obstacles = [o for o in self.obstacles if o.x > -4]

