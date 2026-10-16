import random

from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "beg_food"
    flags = ("is_scratch_for_food",)
    priority = 70
    interval_seconds = (240, 420)

    def on_start(self):
        self.started = False
        self.play(AnimationNode.SCRATCH_SCREEN)

    def on_tick(self):
        if not self.started and self.pet.current_animation_node() == AnimationNode.SCRATCH_SCREEN:
            self.started = True
            self.later(random.randint(1800, 3500), self.finish)

