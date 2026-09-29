"""Copy this single file to behavior_plugins/ and restart the application."""
from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "stretch"

    @classmethod
    def weight(cls, controller):
        return 0.08 if controller.needs.values.energy > 40 else 0.0

    def on_start(self):
        self.started = False
        self.play(AnimationNode.STANDING_IDLE)

    def on_tick(self):
        if not self.started and self.pet.current_animation_node() == AnimationNode.STANDING_IDLE:
            self.started = True
            self.later(1500, self.finish)
