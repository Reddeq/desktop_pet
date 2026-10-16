import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "clean"
    flags = ("is_clean",)

    @classmethod
    def weight(cls, controller):
        return 0.20

    def on_start(self):
        self.phase = "start"
        self.finish_pending = False
        self.play(AnimationNode.CLEAN, PetState.CLEAN)

    def on_tick(self):
        if self.phase == "start" and self.pet.current_animation_node() == AnimationNode.CLEAN:
            self.phase = "clean"
            self.later(random.randint(2000, 5000), self._request_finish)

    def _request_finish(self):
        self.finish_pending = True

    def on_animation_loop_finished(self, node):
        if (node == AnimationNode.CLEAN and self.phase == "clean"
                and self.finish_pending):
            self.phase = "end"
            self.play(AnimationNode.END_CLEAN, PetState.CLEAN)

    def on_animation_finished(self, node):
        if node == AnimationNode.END_CLEAN and self.phase == "end":
            self.finish()
