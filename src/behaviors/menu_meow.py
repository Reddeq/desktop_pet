from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "menu_meow"
    flags = ("is_meow", "is_menu_forced_meow")

    def on_start(self):
        self.play(AnimationNode.MEOW)

    def on_animation_finished(self, node):
        if node == AnimationNode.MEOW:
            self.play(AnimationNode.MEOW)
