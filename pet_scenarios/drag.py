from PyQt6.QtCore import QPoint

from pet_scenarios import BehaviorScenario
from pet_state import PetState


class Drag(BehaviorScenario):
    name = "drag"

    def is_busy(self):
        return self.ctx.is_dragging

    def press(self, global_pos):
        self.controller._reset_motion_flags()
        self.ctx.is_dragging = True
        self.ctx.old_pos = global_pos.toPoint()
        self.pet.set_state(PetState.FALLING)

    def move(self, global_pos):
        if self.ctx.old_pos is None:
            self.ctx.old_pos = global_pos.toPoint()
            return
        delta = QPoint(global_pos.toPoint() - self.ctx.old_pos)
        x, y = self.pet.clamp_position(
            self.pet.x() + delta.x(), self.pet.y() + delta.y()
        )
        if self.pet.current_state != PetState.FALLING:
            self.pet.set_state(PetState.FALLING)
        self.pet.move(x, y)
        self.ctx.old_pos = global_pos.toPoint()

    def release(self):
        self.ctx.is_dragging = False
        self.ctx.old_pos = None
        if self.pet.y() < self.pet.ground_y:
            self.ctx.is_falling = True
            self.ctx.gravity_speed = 0
            self.pet.set_state(PetState.FALLING)
        else:
            self.pet.set_state(PetState.IDLE)

    def cancel(self):
        # Dragging is controlled by mouse release; other scenarios cannot cancel it.
        pass
