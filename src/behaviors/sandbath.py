from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState
import random


class Behavior(Scenario):
    id = 'sandbath'
    interval_seconds = (240, 420)

    def on_start(self):
        self.phase = 'start'
        self.finish_pending = False
        self.play(AnimationNode.SANDBATH, PetState.SANDBATH)

    def on_tick(self):
        if self.phase == 'start' and self.pet.current_animation_node() == AnimationNode.SANDBATH:
            self.phase = 'roll'
            self.later(random.randint(4000, 7000), self._request_finish)

    def _request_finish(self):
        self.finish_pending = True

    def on_animation_loop_finished(self, node):
        if node == AnimationNode.SANDBATH and self.phase == 'roll' and self.finish_pending:
            self.phase = 'end'
            self.play(AnimationNode.END_SANDBATH, PetState.SANDBATH)

    def on_animation_finished(self, node):
        if node == AnimationNode.END_SANDBATH and self.phase == 'end':
            self.finish()
