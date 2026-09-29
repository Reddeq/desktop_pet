from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "meowing"
    flags = ("is_meowing",)

    @classmethod
    def weight(cls, controller):
        return 0.10 if controller.needs.values.mood < 50 else 0.0

    def on_start(self):
        self.play(AnimationNode.MEOWING)

    def on_animation_finished(self, node):
        if node == AnimationNode.MEOWING:
            self.finish()
