import random

from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "food_begging"
    flags = ("is_scratching_for_food",)
    priority = 70
    blocks_cursor = False  # FEED cursor leaving the pet may end the request.

    @classmethod
    def probability(cls, controller, event):
        threshold = controller.ctx.food_begging_satiety_threshold
        satiety = controller.needs.values.satiety
        if event != "logic" or threshold <= 0 or satiety >= threshold:
            return 0.0
        return 0.05 + (threshold - satiety) / threshold * 0.35

    def on_start(self):
        self.started = False
        self.play(AnimationNode.SCRATCHING_SCREEN)

    def on_tick(self):
        if not self.started and self.pet.current_animation_node() == AnimationNode.SCRATCHING_SCREEN:
            self.started = True
            self.later(random.randint(1800, 3500), self.finish)

    def on_needs(self):
        if self.needs.values.satiety >= self.ctx.food_begging_satiety_threshold:
            self.finish()
