"""Bounded reachability graph, launch points and swept jump collision checks."""
from collections import deque
from dataclasses import dataclass
from jump_trajectory import JumpTrajectory
from surfaces import Rect


@dataclass(frozen=True)
class NavigationConfig:
    max_distance: float = 560
    max_rise: float = 420
    arc_height: float = 90
    jump_duration_ms: int = 770  # Fallback; normal playback uses the existing clip timing.
    landing_margin: float = 6
    collision_step: float = 4
    refresh_seconds: float = 1.0
    event_refresh_seconds: float = 0.10
    travel_interval: tuple[float, float] = (25, 55)
    desktop_interaction_chance: float = .20


@dataclass(frozen=True)
class JumpPlan:
    source: str
    target: str
    launch_x: float
    landing_x: float
    trajectory: JumpTrajectory


def clear_trajectory(trajectory, obstacles, width, height, step=4, bounds=None):
    # Bound movement per sample, including a steep descent, to avoid tunneling.
    length = (abs(trajectory.end_x - trajectory.start_x)
              + abs(trajectory.end_y - trajectory.start_y) + 4 * trajectory.height)
    count = max(2, int(length / step) + 1)
    previous = None
    for i in range(count + 1):
        x, foot = trajectory.position(i / count)
        body = Rect(x + .01, foot - height, x + width - .01, foot - .01)
        if bounds is not None and not bounds.contains(body):
            return False
        swept = body if previous is None else Rect(
            min(previous.left, body.left), min(previous.top, body.top),
            max(previous.right, body.right), max(previous.bottom, body.bottom))
        if any(swept.intersects(obstacle) for obstacle in obstacles):
            return False
        previous = body
    return True


class SurfaceNavigator:
    def __init__(self, config=None):
        self.config = config or NavigationConfig()
        self._key = None
        self._graph = {}

    def plan(self, source, target, width, height, obstacles, bounds=None):
        cfg = self.config
        if not source.available or not target.available:
            return None
        if source.id == target.id or source.monitor != target.monitor:
            return None
        if target.right - target.left < width + 2 * cfg.landing_margin:
            return None
        rise = source.y - target.y
        if rise > cfg.max_rise:
            return None
        arcs = (max(cfg.arc_height, abs(rise) / 2 + 30), abs(rise) + cfg.arc_height)
        if rise < 0:
            # Keep the initial upward kick independent of the drop distance.
            # y(t) = start - 4*hop*t + (drop + 4*hop)*t². With no headroom
            # this becomes a downward-only jump, rather than hitting a ceiling.
            headroom = cfg.arc_height if bounds is None else max(0, source.y - height - bounds.top)
            arcs = ((-rise) / 4 + min(cfg.arc_height, headroom),) + arcs
        targets = (target.left + cfg.landing_margin,
                   target.right - width - cfg.landing_margin,
                   (target.left + target.right - width) / 2)
        launches = {source.left, source.right - width,
                    (source.left + source.right - width) / 2}
        for landing in targets:
            for direction in (-1, 1):
                launches.add(source.clamp_x(landing + direction * (width + cfg.arc_height), width))
        choices = sorted(((abs(b - a), a, b) for a in launches for b in targets))
        for distance, launch, landing in choices:
            if distance > cfg.max_distance:
                continue
            for arc in arcs:
                trajectory = JumpTrajectory(launch, source.y, landing, target.y, arc)
                if clear_trajectory(trajectory, obstacles, width, height, cfg.collision_step, bounds):
                    return JumpPlan(source.id, target.id, launch, landing, trajectory)
        return None

    def graph(self, snapshot, width, height):
        key = (snapshot, width, height)
        if key == self._key:
            return self._graph
        graph = {p.id: {} for p in snapshot.platforms}
        for source in snapshot.platforms:
            bounds = next((m.work for m in snapshot.monitors if m.id == source.monitor), None)
            for target in snapshot.platforms:
                obstacles = snapshot.blockers(source.monitor, source.window, target.window,
                                              ignore_source=target.y > source.y)
                plan = self.plan(source, target, width, height, obstacles, bounds)
                if plan:
                    graph[source.id][target.id] = plan
        self._key, self._graph = key, graph
        return graph

    def route(self, snapshot, source, target, width, height):
        graph = self.graph(snapshot, width, height)
        queue = deque([(source, ())])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            if current == target:
                return path
            for neighbor, plan in graph.get(current, {}).items():
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + (plan,)))
        return ()
