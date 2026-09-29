import random
from PyQt6.QtCore import QTimer
from pet_scenarios import BehaviorScenario
from pet_state import PetState


class Cleaning(BehaviorScenario):
    name = "cleaning"
    weight = 0.20

    def __init__(self, controller):
        super().__init__(controller)
        self.timer = QTimer(controller)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.finish)

    def is_busy(self):
        return self.ctx.is_cleaning

    def start(self):
        self.ctx.is_cleaning = True
        self.pet.set_state(PetState.CLEANING)
        if not self.pet.animation_player.has_frames():
            self.finish()
            return
        self.timer.start(random.randint(2000, 5000))

    def finish(self):
        self.cancel()
        self.pet.set_state(PetState.IDLE)

    def cancel(self):
        self.ctx.is_cleaning = False
        self.timer.stop()

    def deactivate(self):
        self.cancel()
