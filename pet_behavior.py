import random

from PyQt6.QtCore import QObject

from pet_state import PetState


class PetBehavior(QObject):
    def __init__(self, controller, pet, ctx, motion, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx
        self.motion = motion

    def is_busy(self) -> bool:
        return (
            self.ctx.is_falling
            or self.ctx.is_walking
            or self.ctx.is_dragging
            or self.ctx.is_recovering
            or self.ctx.is_cleaning
            or self.ctx.is_investigating_notifications
            or self.ctx.is_chasing_cursor
            or self.ctx.is_swatting_cursor
        )

    def tick(self):
        if self.is_busy():
            return

        actions = ["idle", "walk", "cleaning", "investigate_notifications"]
        weights = [0.45, 0.25, 0.20, 0.10]
        new_action = random.choices(actions, weights=weights)[0]

        if new_action == "walk":
            direction = random.choice([-1, 1])
            distance = random.randint(60, 180)
            self.motion.start_walk(direction, distance)

        elif new_action == "cleaning":
            self.controller.start_cleaning()

        elif new_action == "investigate_notifications":
            self.controller.start_notification_investigation()

        else:
            self.pet.set_state(PetState.IDLE)
