from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "sleep"
    flags = ("is_sleeping",)
    priority = 100

    @classmethod
    def probability(cls, controller, event):
        return float(event == "logic" and controller.needs.is_sleepy(controller.ctx.sleep_energy_threshold))

    def on_start(self):
        self.play(AnimationNode.SLEEPING, PetState.SLEEP)

    def on_needs(self):
        if self.needs.values.energy >= 100:
            self.finish()
