"""Behavior modules are discovered automatically at startup."""


class BehaviorScenario:
    name = ""
    weight = 0.0
    priority = False

    def __init__(self, controller):
        self.controller = controller
        self.pet = controller.pet
        self.ctx = controller.ctx
        self.motion = controller.motion

    def can_start(self):
        return True

    def start(self):
        pass

    def is_busy(self):
        return False

    def activate(self):
        pass

    def deactivate(self):
        pass

    def cancel(self):
        pass

    def on_animation_finished(self, animation_name):
        pass

    def on_needs_tick(self):
        pass

    def on_walk_finished(self):
        pass
