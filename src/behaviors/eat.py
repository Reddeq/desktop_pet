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
        self.eat_finish_pending = False
        self.phase = "eat_start"
        self.ctx.is_clean = False
        self.play(AnimationNode.EAT)

    def on_tick(self):
        if self.phase == "eat_start" and self.pet.current_animation_node() == AnimationNode.EAT:
            self.phase = "eat"
            self.later(5000, self._request_finish_eat)
        else:
            super().on_tick()

    def _request_finish_eat(self):
        self.eat_finish_pending = True

    def on_animation_loop_finished(self, node):
        if (node == AnimationNode.EAT and self.phase == "eat"
                and self.eat_finish_pending):
            self.consumed = True
            self.manager.request_once("poop", 60)
            self.ctx.is_clean = True
            super().on_start()
        else:
            super().on_animation_loop_finished(node)

    def on_stop(self):
        if self.consumed:
            self.controller.food_cooldown_until = (
                self.manager._clock() + self.ctx.food_cooldown_seconds
            )
