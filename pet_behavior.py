"""Automatic scenario discovery and scheduling."""
import importlib
import pkgutil
import random
import pet_scenarios
from pet_scenarios import BehaviorScenario


def load_scenarios(controller):
    scenarios = []
    for info in pkgutil.iter_modules(pet_scenarios.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"pet_scenarios.{info.name}")
        scenarios.extend(value(controller) for value in vars(module).values()
                         if isinstance(value, type) and issubclass(value, BehaviorScenario)
                         and value is not BehaviorScenario and value.__module__ == module.__name__)
    return scenarios


class PetBehavior:
    def __init__(self, controller):
        self.controller = controller
        self.scenarios = load_scenarios(controller)
        self.by_name = {s.name: s for s in self.scenarios}
        if len(self.by_name) != len(self.scenarios) or not all(self.by_name):
            raise ValueError("Scenario names must be unique and nonempty")

    def start(self):
        for scenario in self.scenarios:
            scenario.activate()

    def stop(self):
        for scenario in self.scenarios:
            scenario.deactivate()

    def cancel(self):
        for scenario in self.scenarios:
            scenario.cancel()

    def is_busy(self):
        ctx = self.controller.ctx
        return (ctx.is_falling or ctx.is_walking or ctx.is_dragging or ctx.is_recovering
                or any(s.is_busy() for s in self.scenarios))

    def tick(self):
        if self.is_busy():
            return
        for scenario in self.scenarios:
            if scenario.priority and scenario.can_start():
                scenario.start()
                return
        available = [s for s in self.scenarios if s.weight > 0 and s.can_start()]
        if available:
            random.choices(available, weights=[s.weight for s in available])[0].start()

    def on_animation_finished(self, animation_name):
        for scenario in self.scenarios:
            scenario.on_animation_finished(animation_name)

    def on_needs_tick(self):
        for scenario in self.scenarios:
            scenario.on_needs_tick()

    def on_walk_finished(self):
        for scenario in self.scenarios:
            scenario.on_walk_finished()
