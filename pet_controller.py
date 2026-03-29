import random

from PyQt6.QtCore import QObject, QTimer, QPoint

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

        self.walk_direction = 1
        self.walk_target_x = 0
        self.walk_speed = 4

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

    def start(self):
        self.logic_timer.start(5000)
        self.gravity_timer.start(20)
        self.walk_timer.start(16)

    def stop(self):
        self.logic_timer.stop()
        self.gravity_timer.stop()
        self.walk_timer.stop()
        self.cleaning_timer.stop()
        self.dig_timer.stop()

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

    def _reset_motion_flags(self):
        self.is_falling = False
        self.gravity_speed = 0
        self.is_walking = False
        self.is_recovering = False
        self._stop_cleaning()
        self._stop_notification_investigation()

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
        """
        Примерная X-координата у правого нижнего угла экрана.
        Это имитация области уведомлений, а не реальный tray API.
        """
        screen_rect = self.pet.get_current_screen_rect()
        margin = 40
        return screen_rect.x() + screen_rect.width() - self.pet.width() - margin

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

    def pet_logic(self):
        if (
            self.is_falling
            or self.is_walking
            or self.is_dragging
            or self.is_recovering
            or self.is_cleaning
            or self.is_investigating_notifications
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