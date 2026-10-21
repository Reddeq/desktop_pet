"""Beg while the user offers food, without the autonomous request's timer."""
from PyQt6.QtGui import QCursor

from animation_node import AnimationNode
from behavior_runtime import Scenario


class Behavior(Scenario):
    id = 'food_beg'
    flags = ('is_scratch_for_food',)

    def on_start(self):
        self.play(AnimationNode.SCRATCH_SCREEN)

    def on_tick(self):
        if not self.controller.cursor_ai.wants_food(QCursor.pos()):
            self.finish()
