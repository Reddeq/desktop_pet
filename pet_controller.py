import random

from PyQt6.QtCore import QObject, QTimer, QPoint

from pet_behavior import PetBehavior
from pet_context import PetContext
from pet_cursor_ai import PetCursorAI
from pet_motion import PetMotion
from pet_state import PetState


class PetController(QObject):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet
        self.ctx = PetContext()

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self._on_logic_tick)

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

        self.motion = PetMotion(
            controller=self,
            pet=self.pet,
            ctx=self.ctx,
            parent=self,
        )

        self.cursor_ai = PetCursorAI(
            controller=self,
            pet=self.pet,
            ctx=self.ctx,
            parent=self,
        )

        self.behavior = PetBehavior(
            controller=self,
            pet=self.pet,
            ctx=self.ctx,
            motion=self.motion,
            parent=self,
        )

    def start(self):
        self.logic_timer.start(5000)
        self.gravity_timer.start(20)
        self.walk_timer.start(16)
        self.cursor_ai.start()

    def stop(self):
        self.logic_timer.stop()
        self.gravity_timer.stop()
        self.walk_timer.stop()
        self.cleaning_timer.stop()
        self.dig_timer.stop()
        self.cursor_ai.stop()

    def _on_logic_tick(self):
        self.behavior.tick()

    def on_animation_finished(self, animation_name: str):
        try:
            state = PetState(animation_name)
        except ValueError:
            return

        if state == PetState.FALLING_RECOVERY and self.ctx.is_recovering:
            self.motion.finish_fall_recovery()
            return

        if state == PetState.ALERT and self.ctx.is_investigating_notifications:
            self.go_to_notification_area()
            return

    def _stop_cleaning(self):
        self.ctx.is_cleaning = False
        self.cleaning_timer.stop()

    def _stop_notification_investigation(self):
        self.ctx.is_investigating_notifications = False
        self.dig_timer.stop()

    def _reset_motion_flags(self):
        self.ctx.is_falling = False
        self.ctx.gravity_speed = 0
        self.ctx.is_walking = False
        self.ctx.is_recovering = False
        self._stop_cleaning()
        self._stop_notification_investigation()
        self.cursor_ai.cancel()

    def start_notification_investigation(self):
        self._reset_motion_flags()
        self.ctx.is_investigating_notifications = True
        self.pet.set_state(PetState.ALERT)

        if not self.pet.animation_player.has_frames():
            self.go_to_notification_area()

    def go_to_notification_area(self):
        tray_x = self.motion.get_tray_target_x()
        current_x = self.pet.x()

        if tray_x == current_x:
            self.start_dig()
            return

        self.motion.start_run_to_x(tray_x)

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

    def start_cleaning(self):
        self.ctx.is_cleaning = True
        self.pet.set_state(PetState.CLEANING)

        if not self.pet.animation_player.has_frames():
            self.finish_cleaning()
            return

        duration_ms = random.randint(2000, 5000)
        self.cleaning_timer.start(duration_ms)

    def finish_cleaning(self):
        self.ctx.is_cleaning = False
        self.pet.set_state(PetState.IDLE)

    def process_walk_step(self):
        if self.cursor_ai.process_chase_step():
            return

        self.motion.process_walk_step()

    def apply_gravity(self):
        self.motion.apply_gravity()

    def on_mouse_press(self, global_pos):
        self._reset_motion_flags()
        self.ctx.is_dragging = True

        self.ctx.old_pos = global_pos.toPoint()
        self.pet.set_state(PetState.FALLING)

    def on_mouse_move(self, global_pos):
        if self.ctx.old_pos is None:
            self.ctx.old_pos = global_pos.toPoint()
            return

        delta = QPoint(global_pos.toPoint() - self.ctx.old_pos)

        new_x = self.pet.x() + delta.x()
        new_y = self.pet.y() + delta.y()

        new_x, new_y = self.pet.clamp_position(new_x, new_y)

        if self.pet.current_state != PetState.FALLING:
            self.pet.set_state(PetState.FALLING)

        self.pet.move(new_x, new_y)
        self.ctx.old_pos = global_pos.toPoint()

    def on_mouse_release(self):
        self.ctx.is_dragging = False
        self.ctx.old_pos = None

        if self.pet.y() < self.pet.ground_y:
            self.ctx.is_falling = True
            self.ctx.gravity_speed = 0
            self.pet.set_state(PetState.FALLING)
        else:
            self.pet.set_state(PetState.IDLE)