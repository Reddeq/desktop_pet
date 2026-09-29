import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "cleaning"
    flags = ("is_cleaning",)

    @classmethod
    def weight(cls, controller):
        return 0.20

    def on_start(self):
        self.started = False
        self.play(AnimationNode.CLEANING, PetState.CLEANING)

    def on_tick(self):
        if not self.started and self.pet.current_animation_node() == AnimationNode.CLEANING:
            self.started = True
            self.later(random.randint(2000, 5000), self.finish)
