from PyQt6.QtCore import QObject, QTimer, QPoint
from PyQt6.QtGui import QCursor

from pet_state import PetState


class PetCursorAI(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx

        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self.check_cursor_proximity)

        self.chase_timer = QTimer(self)
        self.chase_timer.setSingleShot(True)
        self.chase_timer.timeout.connect(self.finish_cursor_chase)

        self.cursor_chase_cooldown_timer = QTimer(self)
        self.cursor_chase_cooldown_timer.setSingleShot(True)
        self.cursor_chase_cooldown_timer.timeout.connect(self.finish_cursor_chase_cooldown)


    def start(self):
        self.cursor_check_timer.start(120)

    def stop(self):
        self.cursor_check_timer.stop()
        self.chase_timer.stop()
        self.cursor_chase_cooldown_timer.stop()

    def cancel(self):
        self.ctx.is_chasing_cursor = False
        self.ctx.is_swatting_cursor = False
        self.chase_timer.stop()

    def _update_cursor_motion_state(self):
        cursor_pos = QCursor.pos()

        if self.ctx.last_cursor_pos is None:
            self.ctx.last_cursor_pos = cursor_pos
            self.ctx.cursor_still_ticks = 0
            return cursor_pos

        dx = cursor_pos.x() - self.ctx.last_cursor_pos.x()
        dy = cursor_pos.y() - self.ctx.last_cursor_pos.y()
        distance_sq = dx * dx + dy * dy

        threshold_sq = self.ctx.cursor_stationary_threshold * self.ctx.cursor_stationary_threshold

        if distance_sq <= threshold_sq:
            self.ctx.cursor_still_ticks += 1
        else:
            self.ctx.cursor_still_ticks = 0

        self.ctx.last_cursor_pos = cursor_pos
        return cursor_pos

    def _cursor_is_stationary_enough(self) -> bool:
        return self.ctx.cursor_still_ticks >= self.ctx.cursor_stationary_ticks_required

    def _cursor_is_near_pet(self, cursor_pos: QPoint) -> bool:
        pet_center_x = self.pet.x() + self.pet.width() // 2
        pet_center_y = self.pet.y() + self.pet.height() // 2

        dx = cursor_pos.x() - pet_center_x
        dy = cursor_pos.y() - pet_center_y
        distance_sq = dx * dx + dy * dy

        max_distance_sq = self.ctx.cursor_chase_distance * self.ctx.cursor_chase_distance
        return distance_sq <= max_distance_sq

    def _can_swat_cursor(self, cursor_pos: QPoint) -> bool:
        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            front_x = self.pet.x() + self.pet.width() - self.ctx.cursor_front_gap
        else:
            front_x = self.pet.x() + self.ctx.cursor_front_gap

        min_y = self.pet.y() + int(self.pet.height() * 0.40)
        max_y = self.pet.y() + self.pet.height()

        return (
            abs(cursor_pos.x() - front_x) <= self.ctx.swat_reach_x
            and min_y <= cursor_pos.y() <= max_y
        )

    def _get_cursor_chase_target_x(self, cursor_pos: QPoint) -> tuple[int, int]:
        pet_center_x = self.pet.x() + self.pet.width() // 2

        if cursor_pos.x() < pet_center_x - self.ctx.cursor_dead_zone:
            direction = -1
        elif cursor_pos.x() > pet_center_x + self.ctx.cursor_dead_zone:
            direction = 1
        else:
            direction = 1 if self.pet.animation_player.facing_right else -1

        if direction == 1:
            target_x = cursor_pos.x() - (self.pet.width() - self.ctx.cursor_front_gap)
        else:
            target_x = cursor_pos.x() - self.ctx.cursor_front_gap

        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)
        return target_x, direction

    def start_cursor_chase(self):
        self.controller._reset_motion_flags()
        self.ctx.is_chasing_cursor = True
        self.ctx.is_swatting_cursor = False

        self.chase_timer.start(1800)

    def finish_cursor_chase(self):
        self.cancel()
        self.pet.set_state(PetState.IDLE)

        self.ctx.cursor_chase_cooldown = True
        self.cursor_chase_cooldown_timer.start(4000)

    def finish_cursor_chase_cooldown(self):
        self.ctx.cursor_chase_cooldown = False

    def start_cursor_swat(self):
        self.ctx.is_chasing_cursor = False
        self.ctx.is_swatting_cursor = True
        self.ctx.is_walking = False
        self.chase_timer.stop()

        cursor_pos = QCursor.pos()
        self.pet.set_facing_right(cursor_pos.x() >= self.pet.x() + self.pet.width() // 2)
        self.pet.set_state(PetState.SWAT)

        if not self.pet.animation_player.has_frames():
            self.finish_cursor_chase()

    def finish_cursor_swat(self, resume_chase=False):
        self.ctx.is_swatting_cursor = False

        if resume_chase:
            self.start_cursor_chase()
        else:
            self.finish_cursor_chase()

    def check_cursor_proximity(self):
        cursor_pos = self._update_cursor_motion_state()

        if self.ctx.is_swatting_cursor:
            if self._can_swat_cursor(cursor_pos) and self._cursor_is_stationary_enough():
                if self.pet.current_state != PetState.SWAT:
                    self.pet.set_state(PetState.SWAT)
                return

            if self._cursor_is_near_pet(cursor_pos):
                self.finish_cursor_swat(resume_chase=True)
            else:
                self.finish_cursor_swat(resume_chase=False)
            return

        if self.ctx.is_chasing_cursor:
            if self._can_swat_cursor(cursor_pos) and self._cursor_is_stationary_enough():
                self.start_cursor_swat()
            return

        if (
            self.ctx.is_falling
            or self.ctx.is_walking
            or self.ctx.is_dragging
            or self.ctx.is_recovering
            or self.ctx.is_cleaning
            or self.ctx.is_investigating_notifications
            or self.ctx.cursor_chase_cooldown
        ):
            return

        if self._cursor_is_near_pet(cursor_pos):
            if __import__("random").random() < 0.25:
                self.start_cursor_chase()

    def process_chase_step(self) -> bool:
        if self.ctx.is_swatting_cursor:
            return True

        if self.ctx.is_chasing_cursor and not self.ctx.is_dragging:
            cursor_pos = QCursor.pos()
            current_x = self.pet.x()

            target_x, direction = self._get_cursor_chase_target_x(cursor_pos)

            self.pet.set_facing_right(direction == 1)
            self.pet.set_state(PetState.RUN)

            if target_x == current_x:
                return True

            step = self.ctx.cursor_chase_speed * direction
            new_x = current_x + step

            if direction == 1:
                new_x = min(new_x, target_x)
            else:
                new_x = max(new_x, target_x)

            new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
            self.pet.move(new_x, new_y)
            return True

        return False

