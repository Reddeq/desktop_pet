import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "notifications"
    flags = ("is_investigating_notifications",)

    @classmethod
    def weight(cls, controller):
        return 0.10 if controller.needs.values.mood >= 50 else 0.0

    def on_start(self):
        self.phase = "alert"
        self.play(AnimationNode.ALERT, PetState.ALERT)

    def on_animation_finished(self, node):
        if node == AnimationNode.ALERT and self.phase == "alert":
            self.phase = "running"
            self.play(AnimationNode.RUNNING, PetState.RUN)
            self.motion.start_run_to_x(self.motion.get_tray_target_x())

    def on_tick(self):
        node = self.pet.current_animation_node()
        if self.phase == "running" and node == AnimationNode.RUNNING and not self.ctx.is_walking:
            self.phase = "digging_transition"
            self.play(AnimationNode.DIGGING, PetState.DIG)
        elif self.phase == "digging_transition" and node == AnimationNode.DIGGING:
            self.phase = "digging"
            self.later(random.randint(2000, 4000), self.finish)
