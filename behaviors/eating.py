from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "eating"
    flags = ("is_eating",)
    interruptible_by_needs = False

    def on_start(self):
        self.play(AnimationNode.EATING)

    def on_animation_finished(self, node):
        if node == AnimationNode.EATING:
            self.finish()
