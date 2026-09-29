import random
from PyQt6.QtCore import QTimer
from pet_scenarios import BehaviorScenario
from pet_state import PetState


class Notifications(BehaviorScenario):
    name = "notifications"
    weight = 0.10

    def __init__(self, controller):
        super().__init__(controller)
        self.timer = QTimer(controller)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.finish)

    def is_busy(self):
        return self.ctx.is_investigating_notifications

    def start(self):
        self.controller._reset_motion_flags()
        self.ctx.is_investigating_notifications = True
        self.pet.set_state(PetState.ALERT)
        if not self.pet.animation_player.has_frames():
            self.go_to_area()

    def go_to_area(self):
        tray_x = self.motion.get_tray_target_x()
        if tray_x == self.pet.x():
            self.start_dig()
        else:
            self.motion.start_run_to_x(tray_x)

    def start_dig(self):
        self.pet.set_state(PetState.DIG)
        if not self.pet.animation_player.has_frames():
            self.finish()
            return
        self.timer.start(random.randint(2000, 4000))

    def finish(self):
        self.cancel()
        self.pet.set_state(PetState.IDLE)

    def cancel(self):
        self.ctx.is_investigating_notifications = False
        self.timer.stop()

    def deactivate(self):
        self.cancel()

    def on_animation_finished(self, animation_name):
        if animation_name == PetState.ALERT.value and self.is_busy():
            self.go_to_area()

    def on_walk_finished(self):
        if self.is_busy():
            self.start_dig()
