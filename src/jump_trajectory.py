"""Shared jump timing and parabolic root motion for hunts and platforms."""
from dataclasses import dataclass


def flight_progress(progress):
    # Existing jump clip: wind-up 0–1, flight 2–6, landing 7–10.
    return min(1.0, max(0.0, (progress - 2 / 11) / (5 / 11)))


@dataclass(frozen=True)
class JumpTrajectory:
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    height: float

    def position(self, t):
        t = min(1.0, max(0.0, t))
        return (self.start_x + (self.end_x - self.start_x) * t,
                self.start_y + (self.end_y - self.start_y) * t - 4 * self.height * t * (1 - t))
