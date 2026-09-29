"""Autonomous scheduling facade; selection rules live in behavior scripts."""
from PyQt6.QtCore import QObject


class PetBehavior(QObject):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

    def is_busy(self):
        return self.controller.is_busy()

    def tick(self):
        self.controller.behaviors.logic_tick()
