import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "walk"
    blocks_cursor = False

    @classmethod
    def weight(cls, controller):
        return 0.25

    def on_start(self):
        if not self.motion.start_walk(random.choice([-1, 1]), random.randint(60, 180)):
            self.finish()
            return
        self.play(AnimationNode.WALKING, PetState.WALK)

    def on_tick(self):
        if not self.ctx.is_walking:
            self.finish()
