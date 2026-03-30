from PyQt6.QtCore import QObject

from pet_state import PetState


class PetMotion(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx

    def start_walk(self, direction: int, distance: int):
        self.ctx.walk_direction = direction
        self.pet.set_facing_right(direction == 1)
        self.pet.set_state(PetState.WALK)

        target_x = self.pet.x() + (direction * distance)
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == self.pet.x():
            self.pet.set_state(PetState.IDLE)
            return

        self.ctx.walk_target_x = target_x
        self.ctx.is_walking = True

    def start_run_to_x(self, target_x: int):
        current_x = self.pet.x()
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == current_x:
            return

        direction = 1 if target_x > current_x else -1
        self.ctx.walk_direction = direction
        self.ctx.walk_target_x = target_x
        self.ctx.is_walking = True

        self.pet.set_facing_right(direction == 1)
        self.pet.set_state(PetState.RUN)

    def get_tray_target_x(self):
        screen_rect = self.pet.get_current_screen_rect()
        margin = 40
        return screen_rect.x() + screen_rect.width() - self.pet.width() - margin

    def process_walk_step(self):
        if not self.ctx.is_walking or self.ctx.is_dragging:
            return

        current_x = self.pet.x()

        if self.ctx.walk_direction == 1:
            new_x = min(current_x + self.ctx.walk_speed, self.ctx.walk_target_x)
        else:
            new_x = max(current_x - self.ctx.walk_speed, self.ctx.walk_target_x)

        new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
        self.pet.move(new_x, new_y)

        if new_x == self.ctx.walk_target_x:
            self.ctx.is_walking = False

            if self.ctx.is_investigating_notifications:
                self.controller.start_dig()
            else:
                self.pet.set_state(PetState.IDLE)

    def _land(self):
        self.ctx.is_falling = False
        self.ctx.gravity_speed = 0
        self.pet.move(self.pet.x(), self.pet.ground_y)
        self.start_fall_recovery()

    def apply_gravity(self):
        if not self.ctx.is_falling:
            return

        if self.pet.y() < self.pet.ground_y:
            self.ctx.gravity_speed += 2
            new_y = self.pet.y() + self.ctx.gravity_speed

            if new_y >= self.pet.ground_y:
                self._land()
                return

            self.pet.move(self.pet.x(), new_y)
        else:
            self._land()

    def start_fall_recovery(self):
        self.ctx.is_recovering = True
        self.pet.set_state(PetState.FALLING_RECOVERY)

        if not self.pet.animation_player.has_frames():
            self.finish_fall_recovery()

    def finish_fall_recovery(self):
        self.ctx.is_recovering = False
        self.pet.set_state(PetState.IDLE)
