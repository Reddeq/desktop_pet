import random

from PyQt6.QtCore import QObject, QTimer, QPoint
from PyQt6.QtGui import QCursor

from pet_state import PetState


class PetController(QObject):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet

        self.gravity_speed = 0
        self.is_falling = False
        self.is_walking = False
        self.is_dragging = False
        self.is_recovering = False
        self.is_cleaning = False
        self.is_investigating_notifications = False
        self.is_chasing_cursor = False
        self.is_swatting_cursor = False

        self.walk_direction = 1
        self.walk_target_x = 0
        self.walk_speed = 4

        self.cursor_chase_speed = 6
        self.cursor_chase_distance = 160
        self.cursor_chase_cooldown = False

        self.swat_reach_x = 85
        self.cursor_stationary_threshold = 8
        self.cursor_stationary_ticks_required = 2

        self.last_cursor_pos = None
        self.cursor_still_ticks = 0

        self.old_pos = None

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self.pet_logic)

        self.gravity_timer = QTimer(self)
        self.gravity_timer.timeout.connect(self.apply_gravity)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.process_walk_step)

        self.cleaning_timer = QTimer(self)
        self.cleaning_timer.setSingleShot(True)
        self.cleaning_timer.timeout.connect(self.finish_cleaning)

        self.dig_timer = QTimer(self)
        self.dig_timer.setSingleShot(True)
        self.dig_timer.timeout.connect(self.finish_notification_investigation)

        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self.check_cursor_proximity)

        self.chase_timer = QTimer(self)
        self.chase_timer.setSingleShot(True)
        self.chase_timer.timeout.connect(self.finish_cursor_chase)

        self.cursor_chase_cooldown_timer = QTimer(self)
        self.cursor_chase_cooldown_timer.setSingleShot(True)
        self.cursor_chase_cooldown_timer.timeout.connect(self.finish_cursor_chase_cooldown)
        self.cursor_front_gap = 18

    def start(self):
        self.logic_timer.start(5000)
        self.gravity_timer.start(20)
        self.walk_timer.start(16)
        self.cursor_check_timer.start(120)

    def stop(self):
        self.logic_timer.stop()
        self.gravity_timer.stop()
        self.walk_timer.stop()
        self.cleaning_timer.stop()
        self.dig_timer.stop()
        self.cursor_check_timer.stop()
        self.chase_timer.stop()
        self.cursor_chase_cooldown_timer.stop()

    def on_animation_finished(self, animation_name: str):
        try:
            state = PetState(animation_name)
        except ValueError:
            return

        if state == PetState.FALLING_RECOVERY and self.is_recovering:
            self.finish_fall_recovery()
            return

        if state == PetState.ALERT and self.is_investigating_notifications:
            self.go_to_notification_area()
            return

    def _stop_cleaning(self):
        self.is_cleaning = False
        self.cleaning_timer.stop()

    def _stop_notification_investigation(self):
        self.is_investigating_notifications = False
        self.dig_timer.stop()

    def _stop_cursor_chase(self):
        self.is_chasing_cursor = False
        self.is_swatting_cursor = False
        self.chase_timer.stop()

    def _reset_motion_flags(self):
        self.is_falling = False
        self.gravity_speed = 0
        self.is_walking = False
        self.is_recovering = False
        self._stop_cleaning()
        self._stop_notification_investigation()
        self._stop_cursor_chase()

    def _start_walk(self, direction: int, distance: int):
        self.walk_direction = direction
        self.pet.set_facing_right(direction == 1)
        self.pet.set_state(PetState.WALK)

        target_x = self.pet.x() + (direction * distance)
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == self.pet.x():
            self.pet.set_state(PetState.IDLE)
            return

        self.walk_target_x = target_x
        self.is_walking = True

    def _land(self):
        self.is_falling = False
        self.gravity_speed = 0
        self.pet.move(self.pet.x(), self.pet.ground_y)
        self.start_fall_recovery()

    def _get_tray_target_x(self):
        screen_rect = self.pet.get_current_screen_rect()
        margin = 40
        return screen_rect.x() + screen_rect.width() - self.pet.width() - margin

    def _update_cursor_motion_state(self):
        cursor_pos = QCursor.pos()

        if self.last_cursor_pos is None:
            self.last_cursor_pos = cursor_pos
            self.cursor_still_ticks = 0
            return cursor_pos

        dx = cursor_pos.x() - self.last_cursor_pos.x()
        dy = cursor_pos.y() - self.last_cursor_pos.y()
        distance_sq = dx * dx + dy * dy

        if distance_sq <= self.cursor_stationary_threshold * self.cursor_stationary_threshold:
            self.cursor_still_ticks += 1
        else:
            self.cursor_still_ticks = 0

        self.last_cursor_pos = cursor_pos
        return cursor_pos

    def _cursor_is_stationary_enough(self) -> bool:
        return self.cursor_still_ticks >= self.cursor_stationary_ticks_required

    def _can_swat_cursor(self, cursor_pos: QPoint) -> bool:
        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            front_x = self.pet.x() + self.pet.width() - self.cursor_front_gap
        else:
            front_x = self.pet.x() + self.cursor_front_gap

        min_y = self.pet.y() + int(self.pet.height() * 0.40)
        max_y = self.pet.y() + self.pet.height()

        return (
            abs(cursor_pos.x() - front_x) <= self.swat_reach_x
            and min_y <= cursor_pos.y() <= max_y
        )

    def _cursor_is_near_pet(self, cursor_pos: QPoint) -> bool:
        pet_center_x = self.pet.x() + self.pet.width() // 2
        pet_center_y = self.pet.y() + self.pet.height() // 2

        dx = cursor_pos.x() - pet_center_x
        dy = cursor_pos.y() - pet_center_y
        distance_sq = dx * dx + dy * dy

        return distance_sq <= self.cursor_chase_distance * self.cursor_chase_distance

    def start_cleaning(self):
        self.is_cleaning = True
        self.pet.set_state(PetState.CLEANING)

        if not self.pet.animation_player.has_frames():
            self.finish_cleaning()
            return

        duration_ms = random.randint(2000, 5000)
        self.cleaning_timer.start(duration_ms)

    def finish_cleaning(self):
        self.is_cleaning = False
        self.pet.set_state(PetState.IDLE)

    def start_notification_investigation(self):
        self._reset_motion_flags()
        self.is_investigating_notifications = True
        self.pet.set_state(PetState.ALERT)

        if not self.pet.animation_player.has_frames():
            self.go_to_notification_area()

    def go_to_notification_area(self):
        tray_x = self._get_tray_target_x()
        current_x = self.pet.x()

        if tray_x == current_x:
            self.start_dig()
            return

        direction = 1 if tray_x > current_x else -1
        self.walk_direction = direction
        self.walk_target_x = tray_x
        self.is_walking = True

        self.pet.set_facing_right(direction == 1)
        self.pet.set_state(PetState.RUN)

    def start_dig(self):
        self.pet.set_state(PetState.DIG)

        if not self.pet.animation_player.has_frames():
            self.finish_notification_investigation()
            return

        duration_ms = random.randint(2000, 4000)
        self.dig_timer.start(duration_ms)

    def finish_notification_investigation(self):
        self._stop_notification_investigation()
        self.pet.set_state(PetState.IDLE)

    def start_cursor_chase(self):
        self._reset_motion_flags()
        self.is_chasing_cursor = True
        self.is_swatting_cursor = False

        self.chase_timer.start(1800)

    def finish_cursor_chase(self):
        self._stop_cursor_chase()
        self.pet.set_state(PetState.IDLE)

        self.cursor_chase_cooldown = True
        self.cursor_chase_cooldown_timer.start(4000)

    def finish_cursor_chase_cooldown(self):
        self.cursor_chase_cooldown = False

    def start_cursor_swat(self):
        self.is_chasing_cursor = False
        self.is_swatting_cursor = True
        self.is_walking = False
        self.chase_timer.stop()

        cursor_pos = QCursor.pos()
        self.pet.set_facing_right(cursor_pos.x() >= self.pet.x() + self.pet.width() // 2)
        self.pet.set_state(PetState.SWAT)

        if not self.pet.animation_player.has_frames():
            self.finish_cursor_chase()

    def finish_cursor_swat(self, resume_chase=False):
        self.is_swatting_cursor = False

        if resume_chase:
            self.start_cursor_chase()
        else:
            self.finish_cursor_chase()

    def check_cursor_proximity(self):
        cursor_pos = self._update_cursor_motion_state()

        if self.is_swatting_cursor:
            if self._can_swat_cursor(cursor_pos) and self._cursor_is_stationary_enough():
                if self.pet.current_state != PetState.SWAT:
                    self.pet.set_state(PetState.SWAT)
                return

            if self._cursor_is_near_pet(cursor_pos):
                self.finish_cursor_swat(resume_chase=True)
            else:
                self.finish_cursor_swat(resume_chase=False)
            return

        if self.is_chasing_cursor:
            if self._can_swat_cursor(cursor_pos) and self._cursor_is_stationary_enough():
                self.start_cursor_swat()
            return

        if (
            self.is_falling
            or self.is_walking
            or self.is_dragging
            or self.is_recovering
            or self.is_cleaning
            or self.is_investigating_notifications
            or self.cursor_chase_cooldown
        ):
            return

        if self._cursor_is_near_pet(cursor_pos):
            if random.random() < 0.25:
                self.start_cursor_chase()

    def pet_logic(self):
        if (
            self.is_falling
            or self.is_walking
            or self.is_dragging
            or self.is_recovering
            or self.is_cleaning
            or self.is_investigating_notifications
            or self.is_chasing_cursor
            or self.is_swatting_cursor
        ):
            return

        actions = ["idle", "walk", "cleaning", "investigate_notifications"]
        weights = [0.45, 0.25, 0.20, 0.10]
        new_action = random.choices(actions, weights=weights)[0]

        if new_action == "walk":
            direction = random.choice([-1, 1])
            distance = random.randint(60, 180)
            self._start_walk(direction, distance)

        elif new_action == "cleaning":
            self.start_cleaning()

        elif new_action == "investigate_notifications":
            self.start_notification_investigation()

        else:
            self.pet.set_state(PetState.IDLE)

    def process_walk_step(self):
        if self.is_swatting_cursor:
            return

        if self.is_chasing_cursor and not self.is_dragging:
            cursor_pos = QCursor.pos()
            current_x = self.pet.x()

            target_x = self._get_cursor_chase_target_x(cursor_pos)

            if target_x == current_x:
                return

            direction = 1 if target_x > current_x else -1
            self.pet.set_facing_right(direction == 1)
            self.pet.set_state(PetState.RUN)

            step = self.cursor_chase_speed * direction
            new_x = current_x + step

            if direction == 1:
                new_x = min(new_x, target_x)
            else:
                new_x = max(new_x, target_x)

            new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
            self.pet.move(new_x, new_y)
            return

        if not self.is_walking or self.is_dragging:
            return

        current_x = self.pet.x()

        if self.walk_direction == 1:
            new_x = min(current_x + self.walk_speed, self.walk_target_x)
        else:
            new_x = max(current_x - self.walk_speed, self.walk_target_x)

        new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
        self.pet.move(new_x, new_y)

        if new_x == self.walk_target_x:
            self.is_walking = False

            if self.is_investigating_notifications:
                self.start_dig()
            else:
                self.pet.set_state(PetState.IDLE)

    def apply_gravity(self):
        if not self.is_falling:
            return

        if self.pet.y() < self.pet.ground_y:
            self.gravity_speed += 2
            new_y = self.pet.y() + self.gravity_speed

            if new_y >= self.pet.ground_y:
                self._land()
                return

            self.pet.move(self.pet.x(), new_y)
        else:
            self._land()

    def start_fall_recovery(self):
        self.is_recovering = True
        self.pet.set_state(PetState.FALLING_RECOVERY)

        if not self.pet.animation_player.has_frames():
            self.finish_fall_recovery()

    def finish_fall_recovery(self):
        self.is_recovering = False
        self.pet.set_state(PetState.IDLE)

    def on_mouse_press(self, global_pos):
        self._reset_motion_flags()
        self.is_dragging = True

        self.old_pos = global_pos.toPoint()
        self.pet.set_state(PetState.FALLING)

    def on_mouse_move(self, global_pos):
        if self.old_pos is None:
            self.old_pos = global_pos.toPoint()
            return

        delta = QPoint(global_pos.toPoint() - self.old_pos)

        new_x = self.pet.x() + delta.x()
        new_y = self.pet.y() + delta.y()

        new_x, new_y = self.pet.clamp_position(new_x, new_y)

        if self.pet.current_state != PetState.FALLING:
            self.pet.set_state(PetState.FALLING)

        self.pet.move(new_x, new_y)
        self.old_pos = global_pos.toPoint()

    def on_mouse_release(self):
        self.is_dragging = False
        self.old_pos = None

        if self.pet.y() < self.pet.ground_y:
            self.is_falling = True
            self.gravity_speed = 0
            self.pet.set_state(PetState.FALLING)
        else:
            self.pet.set_state(PetState.IDLE)

    def _get_cursor_chase_target_x(self, cursor_pos: QPoint) -> int:
        pet_center_x = self.pet.x() + self.pet.width() // 2

        if cursor_pos.x() >= pet_center_x:
            target_x = cursor_pos.x() - (self.pet.width() - self.cursor_front_gap)
        else:
            target_x = cursor_pos.x() - self.cursor_front_gap

        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)
        return target_x