from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "meow"
    flags = ("is_meow",)

    @classmethod
    def weight(cls, controller):
        return 0.10

    def on_start(self):
        self.play(AnimationNode.MEOW)

    def on_animation_finished(self, node):
        if node == AnimationNode.MEOW:
            self.finish()
