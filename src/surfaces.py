"""Platform geometry in Qt desktop coordinates; no native or Qt dependencies.

All rectangles and intervals are half-open. Window snapshots are in native
pixels, front to back; each monitor maps them to its own Qt coordinate space.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    def intersects(self, other):
        return (self.left < other.right and other.left < self.right
                and self.top < other.bottom and other.top < self.bottom)

    def contains(self, other):
        return (self.left <= other.left and self.right >= other.right
                and self.top <= other.top and self.bottom >= other.bottom)


@dataclass(frozen=True)
class Monitor:
    id: str
    native: Rect
    logical: Rect
    work: Rect
    scale: float = 1.0

    def to_logical(self, rect):
        # Never divide global coordinates by DPR: Qt preserves screen origins
        # on Windows, including negative origins and gaps between screens.
        return Rect(self.logical.left + (rect.left - self.native.left) / self.scale,
                    self.logical.top + (rect.top - self.native.top) / self.scale,
                    self.logical.left + (rect.right - self.native.left) / self.scale,
                    self.logical.top + (rect.bottom - self.native.top) / self.scale)


@dataclass(frozen=True)
class Window:
    handle: int
    rect: Rect
    visible: bool = True
    minimized: bool = False
    cloaked: bool = False
    own: bool = False
    utility: bool = False
    desktop: bool = False

    @property
    def occludes(self):
        return self.visible and not (self.minimized or self.cloaked or self.own or self.desktop)

    @property
    def suitable(self):
        return self.occludes and not self.utility


@dataclass(frozen=True)
class Platform:
    id: str
    kind: str
    left: float
    right: float
    y: float
    monitor: str
    window: int | None = None
    origin: tuple[float, float] = (0, 0)
    available: bool = True

    def fits(self, x, width):
        return self.available and self.left <= x and x + width <= self.right

    def clamp_x(self, x, width):
        return max(self.left, min(x, self.right - width))


@dataclass(frozen=True)
class SurfaceSnapshot:
    platforms: tuple[Platform, ...]
    # Visible native window rectangles, transformed separately per monitor.
    obstacles: tuple[tuple[str, Rect], ...]
    fullscreen: frozenset[str] = frozenset()
    monitors: tuple[Monitor, ...] = ()
    window_ids: tuple[int, ...] = ()

    def blockers(self, monitor, source_window=None, target_window=None, ignore_source=False):
        entries = [(index, rect) for index, (sid, rect) in enumerate(self.obstacles) if sid == monitor]
        if not self.window_ids:
            return [rect for _, rect in entries]
        # This is a 2-D desktop: windows behind the supporting window are its
        # backdrop, not walls through the pet's already valid standing pose.
        # From the desktop, the destination establishes that stacking layer.
        anchor = source_window if source_window is not None else target_window
        cutoff = next((i for i, _ in entries if self.window_ids[i] == anchor), None)
        return [rect for i, rect in entries
                if (cutoff is None or i <= cutoff or self.window_ids[i] == target_window)
                and not (ignore_source and self.window_ids[i] == source_window)]


def subtract_interval(segments, left, right):
    result = []
    for a, b in segments:
        if right <= a or left >= b:
            result.append((a, b))
        else:
            if a < left:
                result.append((a, left))
            if right < b:
                result.append((right, b))
    return result


def build_surfaces(windows, monitors, width, height, foreground=None):
    platforms, obstacles, fullscreen, window_ids = [], [], set(), []
    for monitor in monitors:
        work = monitor.work
        platforms.append(Platform(f'desktop:{monitor.id}', 'desktop', work.left,
                                  work.right, work.bottom, monitor.id))
        above = []
        for window in windows:
            if not window.occludes or not window.rect.intersects(monitor.native):
                continue
            rect = monitor.to_logical(window.rect)
            obstacles.append((monitor.id, rect))
            window_ids.append(window.handle)
            if window.handle == foreground and window.rect.contains(monitor.native):
                fullscreen.add(monitor.id)
            if (window.suitable and work.top + height <= rect.top < work.bottom):
                segments = [(max(work.left, rect.left), min(work.right, rect.right))]
                # Test the entire sprite-height strip, not only a one-pixel
                # title bar. A window just above the edge also blocks a pet.
                for blocker in above:
                    if blocker.bottom > rect.top - height and blocker.top <= rect.top:
                        segments = subtract_interval(segments, blocker.left, blocker.right)
                for index, (left, right) in enumerate(segments):
                    if right - left >= width:
                        platforms.append(Platform(
                            f'window:{window.handle}:{monitor.id}:{index}', 'window',
                            left, right, rect.top, monitor.id, window.handle,
                            (rect.left, rect.top)))
            above.append(rect)
    return SurfaceSnapshot(tuple(platforms), tuple(obstacles), frozenset(fullscreen),
                           tuple(monitors), tuple(window_ids))
