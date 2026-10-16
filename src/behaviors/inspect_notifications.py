import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "inspect_notifications"
    flags = ("is_inspect_notifications",)

    @classmethod
    def weight(cls, controller):
        return 0.10

    def on_start(self):
        self.dig_finish_pending = False
        self.phase = "alert"
        self.play(AnimationNode.ALERT, PetState.ALERT)

    def on_animation_finished(self, node):
        if node == AnimationNode.ALERT and self.phase == "alert":
            self.phase = "run"
            self.play(AnimationNode.RUN, PetState.RUN)
            self.motion.start_run_to_x(self.motion.get_tray_target_x())
        elif node == AnimationNode.END_DIG and self.phase == "dig_end":
            self.finish()

    def on_tick(self):
        node = self.pet.current_animation_node()
        if self.phase == "run" and node == AnimationNode.RUN and not self.ctx.is_walk:
            self.phase = "dig_transition"
            self.play(AnimationNode.DIG, PetState.DIG)
        elif self.phase == "dig_transition" and node == AnimationNode.DIG:
            self.phase = "dig"
            self.later(random.randint(2000, 4000), self._request_finish_dig)

    def _request_finish_dig(self):
        self.dig_finish_pending = True

    def on_animation_loop_finished(self, node):
        if (node == AnimationNode.DIG and self.phase == "dig"
                and self.dig_finish_pending):
            self.phase = "dig_end"
            self.play(AnimationNode.END_DIG, PetState.DIG)
