from animation_node import AnimationNode
from behaviors.clean import Behavior as CleanBehavior


class Behavior(CleanBehavior):
    id = "eat"
    flags = ("is_eat", "is_clean")

    @classmethod
    def weight(cls, controller):
        # Feeding is an explicit interaction, unlike autonomous cleaning.
        return 0.0

    def on_start(self):
        self.consumed = False
        self.phase = "eat"
        self.ctx.is_clean = False
        self.play(AnimationNode.EAT)

    def on_animation_finished(self, node):
        if node == AnimationNode.EAT and self.phase == "eat":
            self.consumed = True
            self.ctx.is_clean = True
            super().on_start()
        else:
            super().on_animation_finished(node)

    def on_stop(self):
        if self.consumed:
            self.controller.food_cooldown_until = (
                self.manager._clock() + self.ctx.food_cooldown_seconds
            )
