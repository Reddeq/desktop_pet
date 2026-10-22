"""Snapshot cache, moving-platform attachment and integration with pet motion."""
from dataclasses import replace
import logging
import random
import time

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtGui import QGuiApplication, QScreen

from surfaces import Monitor, Rect, SurfaceSnapshot, build_surfaces
from surface_navigation import NavigationConfig, SurfaceNavigator, clear_trajectory
from surface_travel import SurfaceTravel
from windows_tracker import WindowsTracker
from surface_entry import top_entries

log = logging.getLogger(__name__)


def qt_rect(rect):
    return Rect(rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())


def screen_id(screen):
    r = screen.geometry()
    return f'{screen.name()}@{r.x()},{r.y()}'


class SurfaceController(QObject):
    def __init__(self, controller, tracker=None, config=None):
        super().__init__(controller)
        self.controller = controller
        self.pet = controller.pet
        self.config = config or NavigationConfig()
        self.navigator = SurfaceNavigator(self.config)
        self.tracker = tracker  # Native resources are allocated only on opt-in.
        self.clock = time.monotonic
        self.enabled = False
        self.current = None
        self.snapshot = SurfaceSnapshot((), ())
        self.monitors = ()
        self.travel = SurfaceTravel(self)
        self.destination = None
        self.next_travel = 0
        self.last_refresh = -float('inf')
        self.fullscreen_hidden = False
        self.error = None
        application = QGuiApplication.instance()
        if application is not None:
            for screen in application.screens():
                self._watch_screen(screen)
            application.screenAdded.connect(self._watch_screen)
            application.screenAdded.connect(self.invalidate)
            application.screenRemoved.connect(self.invalidate)

    @pyqtSlot(QScreen)
    def _watch_screen(self, screen):
        for signal in (screen.geometryChanged, screen.availableGeometryChanged,
                       screen.logicalDotsPerInchChanged):
            signal.connect(self.invalidate)

    @property
    def on_window(self):
        return self.current is not None and self.current.kind == 'window'

    @property
    def elevated(self):
        return self.current is not None and self.current.kind != 'desktop'

    def set_enabled(self, enabled):
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.tracker = self.tracker or WindowsTracker()
            self.tracker.start()
            self.refresh()
            self.next_travel = self.clock() + random.uniform(*self.config.travel_interval)
        else:
            self.close()
            self.destination = None
            if self.elevated or self.travel.active:
                self.fall()

    @pyqtSlot()
    def invalidate(self):
        if self.tracker is not None:
            self.tracker.dirty.set()
        self.last_refresh = -float('inf')

    def close(self):
        if self.tracker is not None:
            self.tracker.close()
        if self.fullscreen_hidden:
            self.fullscreen_hidden = False
            if not self.controller.ctx.is_hidden_offscreen:
                self.pet.show()

    def _monitors(self):
        native = self.tracker.monitor_rects()
        monitors = []
        for screen in QGuiApplication.screens():
            logical = qt_rect(screen.geometry())
            physical = native.get(screen.name())
            if physical is None:
                physical = next((r for r in native.values()
                                 if r.left == logical.left and r.top == logical.top), None)
            if physical is None:
                # A stale/missing monitor mapping is unsafe at mixed DPI.
                continue
            monitors.append(Monitor(screen_id(screen), physical, logical,
                                    qt_rect(screen.availableGeometry()), screen.devicePixelRatio()))
        return tuple(monitors)

    def refresh(self):
        try:
            self.tracker.dirty.clear()
            self.monitors = self._monitors()
            windows, foreground = self.tracker.scan()
            self.snapshot = build_surfaces(windows, self.monitors, self.pet.width(),
                                           self.pet.height(), foreground)
            self.error = None
        except (OSError, RuntimeError) as exc:
            self.error = str(exc)
            log.warning('Window platform discovery failed: %s', exc)
            self.snapshot = SurfaceSnapshot((), ())
        self.last_refresh = self.clock()
        if self.controller.ctx.is_fall:
            self.prepare_drop()
        if self.travel.active:
            self.travel.revalidate()
        elif (self.on_window and not self.controller.ctx.is_drag and not self.controller.ctx.is_fall
              and self.controller.cursor_ai.jump.phase not in {'jump', 'jump_transition'}):
            candidates = [p for p in self.snapshot.platforms if p.window == self.current.window
                          and p.fits(self.pet.x(), self.pet.width())
                          and abs(p.y - (self.pet.y() + self.pet.height())) <= 2]
            if candidates:
                # Preserve the unrounded window-relative offset accumulated by
                # attachment, rather than re-deriving it from rounded pixels.
                self.current = candidates[0]
                self.pet.ground_y = self.ground_y()
            else:
                self.fall()

    def by_id(self, platform_id):
        return next((p for p in self.snapshot.platforms if p.id == platform_id), None)

    def top_entries(self):
        return top_entries(self.snapshot, self.desktop().monitor, self.pet.width(),
                           self.pet.height(), self.config.landing_margin)

    def request_desktop_behavior(self, behavior_id):
        if (not self.enabled or not self.elevated or self.controller.interaction_locked
                or random.random() >= self.config.desktop_interaction_chance):
            return False
        target = self.desktop()
        obstacles = self.snapshot.blockers(self.current.monitor, self.current.window,
                                          ignore_source=True)
        monitor = next((m for m in self.monitors if m.id == self.current.monitor), None)
        if monitor is None:
            return False
        plan = self.navigator.plan(self.current, target, self.pet.width(), self.pet.height(),
                                   obstacles, monitor.work)
        if plan is None:
            return False
        self.destination = None
        return self.travel.begin(plan, after_behavior=behavior_id)

    def desktop(self):
        screen = self.pet.get_current_screen_rect()
        # Legacy bottom edge remains available even if native discovery fails.
        from surfaces import Platform
        sid = screen_id(self.pet.get_active_clamp_screen()) if hasattr(self.pet, 'get_active_clamp_screen') else 'test'
        return next((p for p in self.snapshot.platforms if p.kind == 'desktop' and p.monitor == sid),
                    Platform(f'desktop:{sid}', 'desktop', screen.left(), screen.right() + 1,
                             screen.bottom() + 1, sid))

    def ground_y(self):
        if self.controller.ctx.is_fall and hasattr(self, 'fall_target'):
            return round(self.fall_target.y - self.pet.height())
        surface = self.current if self.elevated else self.desktop()
        return round(surface.y - self.pet.height())

    def clamp(self, x, y):
        if not self.elevated or self.controller.ctx.is_drag or self.travel.phase == 'jump':
            return None
        screen = self.pet.get_current_screen_rect()
        return (round(self.current.clamp_x(x, self.pet.width())),
                max(screen.top(), min(y, self.ground_y())))

    def attach(self, platform):
        self.current = platform
        self.pet.ground_y = self.ground_y()
        self.offset = self.pet.x() - platform.origin[0]
        self.last_x = self.pet.x()
        if hasattr(self.pet, 'bind_to_screen'):
            screen = next((s for s in QGuiApplication.screens() if screen_id(s) == platform.monitor), None)
            if screen is not None:
                self.pet.bind_to_screen(screen)

    def detach(self):
        self.current = None
        self.destination = None

    def prepare_drop(self):
        self.current = None
        foot = self.pet.y() + self.pet.height()
        desktop = self.desktop()
        candidates = [p for p in self.snapshot.platforms
                      if (self.enabled or p.kind == 'desktop') and p.fits(self.pet.x(), self.pet.width())
                      and p.monitor == desktop.monitor and p.y >= foot - 1]
        candidates.append(desktop)
        self.fall_target = min(candidates, key=lambda p: p.y)
        self.pet.ground_y = round(self.fall_target.y - self.pet.height())

    def fall(self):
        self.travel.cancel()
        if self.on_window:
            # A fast visibility/size check can precede the coalesced full scan.
            # Do not immediately land on the stale surface we just lost.
            lost = self.current.window
            self.snapshot = replace(self.snapshot, platforms=tuple(
                p for p in self.snapshot.platforms if p.window != lost))
        self.detach()
        self.prepare_drop()
        desktop = self.desktop()
        # A disconnected monitor can leave the pet wholly outside every
        # available screen. Only this emergency recovery clamps its position.
        if not desktop.fits(self.pet.x(), self.pet.width()):
            self.pet.move(round(desktop.clamp_x(self.pet.x(), self.pet.width())),
                          min(self.pet.y(), round(desktop.y - self.pet.height())))
            self.prepare_drop()
        self.controller.start_fall()

    def land_from_fall(self):
        target = getattr(self, 'fall_target', None)
        if target is not None:
            self.attach(target)
        elif self.enabled:
            self.attach(self.desktop())

    def _follow(self):
        if (not self.on_window or self.travel.phase == 'jump'
                or self.controller.cursor_ai.jump.phase in {'jump', 'jump_transition'}):
            return
        current = self.current
        window = self.tracker.window(current.window)
        monitor = next((m for m in self.monitors if m.id == current.monitor), None)
        if window is None or monitor is None:
            self.fall()
            return
        rect = monitor.to_logical(window.rect)
        # Record walking deltas only. Window movement always uses the absolute
        # native origin + fixed offset; fractional DPI rounding cannot drift.
        previous_x = self.pet.x()
        self.offset += previous_x - self.last_x
        dx, dy = rect.left - current.origin[0], rect.top - current.origin[1]
        updated = replace(current, left=current.left + dx, right=current.right + dx,
                          y=rect.top, origin=(rect.left, rect.top))
        x = round(rect.left + self.offset)
        body = Rect(x, updated.y - self.pet.height(), x + self.pet.width(), updated.y)
        if not monitor.work.contains(body):
            # An attached window may cross to another monitor. Recompute from
            # that monitor's native origin/DPR, never interpolate global DPI.
            replacement = None
            for candidate in self.monitors:
                other = candidate.to_logical(window.rect)
                other_x = round(other.left + self.offset)
                other_body = Rect(other_x, other.top - self.pet.height(),
                                  other_x + self.pet.width(), other.top)
                if window.rect.intersects(candidate.native) and candidate.work.contains(other_body):
                    replacement = candidate, other, other_x
                    break
            if replacement is not None:
                monitor, rect, x = replacement
                updated = replace(current, monitor=monitor.id, left=rect.left, right=rect.right,
                                  y=rect.top, origin=(rect.left, rect.top))
                if hasattr(self.pet, 'bind_to_screen'):
                    screen = next((s for s in QGuiApplication.screens() if screen_id(s) == monitor.id), None)
                    if screen is not None:
                        self.pet.bind_to_screen(screen)
                body = Rect(x, rect.top - self.pet.height(), x + self.pet.width(), rect.top)
        if (not monitor.work.contains(body) or rect.width < self.pet.width()
                or body.left < rect.left or body.right > rect.right):
            self.fall()
            return
        self.current = updated
        self.pet.ground_y = self.ground_y()
        self.pet.move(x, self.pet.ground_y)
        if self.controller.ctx.is_walk:
            self.controller.ctx.walk_target_x += x - previous_x
        self.last_x = x

    def clear_jump(self, trajectory, target=None):
        surface = self.current or self.desktop()
        obstacles = self.snapshot.blockers(surface.monitor, surface.window,
                                          target.window if target is not None else None,
                                          ignore_source=trajectory.end_y > trajectory.start_y)
        monitor = next((m for m in self.monitors if m.id == surface.monitor), None)
        if monitor is None:
            return False
        for i in range(101):
            x, y = trajectory.position(i / 100)
            if not monitor.work.contains(Rect(x, y - self.pet.height(), x + self.pet.width(), y)):
                return False
        return clear_trajectory(trajectory, obstacles, self.pet.width(), self.pet.height(),
                                self.config.collision_step)

    def after_transfer(self):
        if self.current and self.current.id == self.destination:
            self.destination = None
        self.next_travel = self.clock() + (random.uniform(5, 10) if self.destination
                                           else random.uniform(*self.config.travel_interval))

    def _choose_route(self):
        source = self.current or self.desktop()
        targets = list(self.snapshot.platforms)
        random.shuffle(targets)
        if self.destination:
            targets.sort(key=lambda p: p.id != self.destination)
        for target in targets:
            if target.id == source.id:
                continue
            route = self.navigator.route(self.snapshot, source.id, target.id,
                                          self.pet.width(), self.pet.height())
            if route and self.clear_jump(route[0].trajectory, self.by_id(route[0].target)):
                self.destination = target.id
                self.travel.begin(route[0])
                return

    def tick(self):
        if not self.enabled:
            return False
        now = self.clock()
        if self.controller.ctx.is_fall:
            # Re-evaluate moving/vanished landing surfaces before each gravity
            # step, but never pull the pet upwards to a surface already passed.
            self.prepare_drop()
        elif not self.controller.ctx.is_drag:
            self._follow()
        due = now - self.last_refresh
        if (due >= self.config.refresh_seconds
                or self.tracker.dirty.is_set() and due >= self.config.event_refresh_seconds):
            self.refresh()
        current = self.current or self.desktop()
        fullscreen = current.monitor in self.snapshot.fullscreen
        if fullscreen and not self.controller.ctx.is_drag:
            if self.pet.isVisible():
                self.pet.hide()
                self.fullscreen_hidden = True
            return True
        if self.fullscreen_hidden:
            self.fullscreen_hidden = False
            if not self.controller.ctx.is_hidden_offscreen:
                self.pet.show()
        if self.travel.active:
            self.travel.tick(now)
            return True
        if now >= self.next_travel and not self.controller.is_busy():
            self.after_transfer()
            self._choose_route()
            return self.travel.active
        return False
