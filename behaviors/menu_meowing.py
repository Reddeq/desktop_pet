from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "menu_meowing"
    flags = ("is_meowing", "is_menu_forced_meowing")
    interruptible_by_needs = False

    def on_start(self):
        self.play(AnimationNode.MEOWING)

    def on_animation_finished(self, node):
        if node == AnimationNode.MEOWING:
            self.play(AnimationNode.MEOWING)
