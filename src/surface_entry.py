"""Choose an unobstructed vertical entrance from above a monitor."""
from dataclasses import dataclass
from surfaces import Platform, Rect, subtract_interval


@dataclass(frozen=True)
class TopEntry:
    platform: Platform
    x: float
    top: float


def top_entries(snapshot, monitor_id, width, height, margin=6):
    monitor = next((m for m in snapshot.monitors if m.id == monitor_id), None)
    if monitor is None or monitor_id in snapshot.fullscreen:
        return ()
    entries = []
    for target in snapshot.platforms:
        if target.kind != 'window' or target.monitor != monitor_id or not target.available:
            continue
        segments = [(target.left, target.right)]
        for blocker in snapshot.blockers(monitor_id, target_window=target.window):
            if blocker.top < target.y and blocker.bottom > monitor.logical.top:
                segments = subtract_interval(segments, blocker.left, blocker.right)
        # Gravity lands on the first eligible surface below the feet, even if
        # another window is behind the destination in Z-order.
        for other in snapshot.platforms:
            if other.available and other.monitor == monitor_id and other.kind == 'window' and other.y < target.y:
                segments = subtract_interval(segments, other.left, other.right)
        for left, right in segments:
            if right - left >= width + 2 * margin:
                x = (left + right - width) / 2
                body = Rect(x, target.y - height, x + width, target.y)
                if monitor.work.contains(body):
                    entries.append(TopEntry(target, x, monitor.logical.top))
    return tuple(entries)
