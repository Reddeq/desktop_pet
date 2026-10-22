"""Lifecycle and discovery for independently installed behavior scripts."""
import importlib
import importlib.util
import logging
import math
import pkgutil
import random
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer

import behaviors
from animation_node import AnimationNode
from pet_state import PetState

log = logging.getLogger(__name__)


class Scenario(QObject):
    """Export a subclass as ``Behavior`` in a behaviors/*.py file.

    Instances live for one run. Use later() for owned, cancellable timers and
    finish() to release the pet. All hooks run on the Qt main thread.
    """

    id = ""
    flags = ()  # Compatibility flags for existing UI; new scripts need none.
    blocks_cursor = True
    preserve_on_menu = False
    interval_seconds = None  # Optional (minimum, maximum) delay between starts.
    priority = 0
    requires_desktop = False

    def __init__(self, manager):
        super().__init__(manager)
        self.manager = manager
        self.controller = manager.controller
        self.pet = self.controller.pet
        self.ctx = self.controller.ctx
        self.motion = self.controller.motion
        self._timers = set()

    @classmethod
    def weight(cls, controller):
        """Relative weight in the idle autonomous lottery; zero disables it."""
        return 0.0

    @classmethod
    def probability(cls, controller, event):
        """Optional priority trigger evaluated on 'logic' ticks."""
        return 0.0

    @classmethod
    def can_start(cls, controller):
        return True

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def on_tick(self):
        """Called after horizontal movement, approximately every 16 ms."""

    def on_animation_finished(self, node):
        pass

    def on_animation_loop_finished(self, node):
        pass

    def later(self, milliseconds, callback):
        if self.manager.active is not self:
            return None
        timer = QTimer(self)
        timer.setSingleShot(True)
        self._timers.add(timer)

        def fire():
            self._timers.discard(timer)
            timer.deleteLater()
            if self.manager.active is self:
                self.manager.invoke(self, callback)

        timer.timeout.connect(fire)
        timer.start(milliseconds)
        return timer

    def play(self, node, state=PetState.IDLE):
        self.controller._set_logical_state(state)
        self.pet.play_node(node, replace=True, force_restart=True)
        if self.manager.active is not self:
            # A synchronous animation_failed signal may have canceled this run.
            # Stop the hook before it can start movement or create other effects.
            raise RuntimeError(f"Animation request canceled scenario {self.id}")

    def finish(self, go_idle=True):
        self.manager.finish(self, go_idle=go_idle)

    def _dispose(self):
        for timer in self._timers:
            timer.stop()
        self._timers.clear()
        try:
            self.on_stop()
        finally:
            for flag in self.flags:
                setattr(self.ctx, flag, False)
            self.deleteLater()


class BehaviorManager(QObject):
    def __init__(self, controller, plugin_dirs=None):
        super().__init__(controller)
        self.controller = controller
        self.active = None
        self.registry = {}
        self.errors = []
        self.disabled = set()
        self._clock = time.monotonic
        self._next_due = {}
        self._discover(plugin_dirs)
        for behavior_id in self.registry:
            self.postpone(behavior_id)

    def _register(self, module):
        cls = getattr(module, "Behavior", None)
        if not isinstance(cls, type) or not issubclass(cls, Scenario):
            raise ValueError("Script must export Behavior, a Scenario subclass")
        if not isinstance(cls.id, str) or not cls.id or cls.id in self.registry:
            raise ValueError(f"Invalid or duplicate behavior id: {cls.id!r}")
        if not isinstance(cls.priority, (int, float)) or not math.isfinite(cls.priority):
            raise ValueError("Behavior priority must be finite")
        interval = cls.interval_seconds
        if interval is not None:
            if (not isinstance(interval, (tuple, list)) or len(interval) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float))
                           or not math.isfinite(v) or v <= 0 for v in interval)
                    or interval[0] > interval[1]):
                raise ValueError("interval_seconds must be a positive ordered pair")
        self.registry[cls.id] = cls

    def postpone(self, behavior_id):
        """Choose a fresh delay; due actions wait until the pet becomes free."""
        interval = self.registry[behavior_id].interval_seconds
        if interval is not None:
            self._next_due[behavior_id] = self._clock() + random.uniform(*interval)

    def schedule_snapshot(self):
        now = self._clock()
        return {name: max(0, due - now) for name, due in self._next_due.items()
                if name not in self.disabled}

    def _error(self, source, exc):
        message = f"{source}: {exc}"
        self.errors.append(message)
        log.exception("Behavior error: %s", message)

    def _discover(self, plugin_dirs):
        for info in sorted(pkgutil.iter_modules(behaviors.__path__), key=lambda x: x.name):
            if info.name.startswith("_") or info.ispkg:
                continue
            try:
                self._register(importlib.import_module(f"behaviors.{info.name}"))
            except Exception as exc:
                self._error(info.name, exc)

        if plugin_dirs is None:
            root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
            plugin_dirs = [root / "behavior_plugins"]
        for directory in plugin_dirs:
            for path in sorted(Path(directory).glob("*.py")):
                if path.name.startswith("_"):
                    continue
                name = f"_pet_plugin_{path.stem}_{len(self.registry)}"
                try:
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[name] = module
                    spec.loader.exec_module(module)
                    self._register(module)
                except Exception as exc:
                    sys.modules.pop(name, None)
                    self._error(path, exc)

    @property
    def blocks_cursor(self):
        return self.active is not None and self.active.blocks_cursor

    def invoke(self, scenario, callback, *args):
        try:
            callback(*args)
        except Exception as exc:
            self.disabled.add(scenario.id)
            self._error(scenario.id, exc)
            self.finish(scenario)

    def start(self, behavior_id):
        cls = self.registry.get(behavior_id)
        if cls is None or behavior_id in self.disabled:
            return False
        try:
            eligible = cls.can_start(self.controller)
        except Exception as exc:
            self.disabled.add(behavior_id)
            self._error(behavior_id, exc)
            return False
        if not eligible:
            self.postpone(behavior_id)
            return False
        if self.controller.surfaces.elevated and cls.requires_desktop:
            accepted = self.controller.surfaces.request_desktop_behavior(behavior_id)
            # A missed scheduled interaction is skipped for this occurrence,
            # rather than rerolling the 20% chance every five seconds.
            self.postpone(behavior_id)
            return accepted
        # Construct before interrupting the old behavior in case construction fails.
        try:
            scenario = cls(self)
        except Exception as exc:
            self.disabled.add(behavior_id)
            self._error(behavior_id, exc)
            return False
        self.controller._reset_motion_flags()
        self.active = scenario
        for flag in scenario.flags:
            setattr(self.controller.ctx, flag, True)
        self.invoke(scenario, scenario.on_start)
        if behavior_id not in self.disabled:
            self.postpone(behavior_id)
        return behavior_id not in self.disabled

    def cancel(self):
        scenario, self.active = self.active, None
        if scenario is not None:
            try:
                scenario._dispose()
            except Exception as exc:
                self._error(scenario.id, exc)
        self.controller.motion.stop_horizontal_motion()

    def finish(self, scenario, go_idle=True):
        if self.active is not scenario:
            return
        self.cancel()
        if go_idle:
            self.controller.start_idle()

    def dispatch(self, hook, *args):
        scenario = self.active
        if scenario is not None:
            self.invoke(scenario, getattr(scenario, hook), *args)

    def _score(self, cls, method, *args):
        if cls.id in self.disabled:
            return 0.0
        try:
            value = float(getattr(cls, method)(self.controller, *args))
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid {method}: {value}")
            return value
        except Exception as exc:
            self.disabled.add(cls.id)
            self._error(cls.id, exc)
            return 0.0

    def _trigger(self, event):
        for cls in sorted(self.registry.values(), key=lambda cls: (-cls.priority, cls.id)):
            if self.active is not None and cls.id == self.active.id:
                continue
            probability = self._score(cls, "probability", event)
            if probability > 0 and random.random() < min(1.0, probability):
                if self.start(cls.id):
                    return True
        return False

    def logic_tick(self):
        if self.controller.is_busy():
            return
        now = self._clock()
        due = [self.registry[name] for name, deadline in self._next_due.items()
               if deadline <= now and name not in self.disabled]
        for cls in sorted(due, key=lambda cls: (-cls.priority, self._next_due[cls.id], cls.id)):
            if self.start(cls.id):
                return
        if self._trigger("logic"):
            return
        candidates = list(self.registry.values())
        weights = [self._score(cls, "weight") for cls in candidates]
        maximum = max(weights, default=0)
        if maximum > 0:
            # Individually finite plugin weights can overflow when summed.
            weights = [weight / maximum for weight in weights]
            self.start(random.choices(candidates, weights=weights)[0].id)

