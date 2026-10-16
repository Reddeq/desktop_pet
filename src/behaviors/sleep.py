import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "sleep"
    flags = ("is_sleep",)
    priority = 100
    interval_seconds = (600, 900)
    duration_seconds = (30, 60)

    def on_start(self):
        self.started = False
        self.wake_pending = False
        self.play(AnimationNode.SLEEP, PetState.SLEEP)

    def on_tick(self):
        if not self.started and self.pet.current_animation_node() == AnimationNode.SLEEP:
            self.started = True
            self.later(random.randint(*self.duration_seconds) * 1000, self._request_wake)

    def _request_wake(self):
        self.wake_pending = True

    def on_animation_loop_finished(self, node):
        if node == AnimationNode.SLEEP and self.wake_pending:
            self.finish()

