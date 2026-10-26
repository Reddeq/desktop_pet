"""The landing, short cursor capture and dig part of a cursor hunt."""
import time

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QCursor

from animation_node import AnimationNode as N
from pet_state import PetState
from jump_trajectory import JumpTrajectory, flight_progress


class CursorJump(QObject):
    def __init__(self, ai):
        super().__init__(ai)
        self.ai = ai
        self.pet = ai.pet
        self.ctx = ai.ctx
        self.controller = ai.controller
        self.clock = time.monotonic
        self.cooldown_until = 0.0
        self.phase = None
        self.holding = False
        self.captured = False
        self.finish_pending = False
        self.release_timer = QTimer(self)
        self.release_timer.setSingleShot(True)
        self.release_timer.timeout.connect(self.release)
        self.dig_timer = QTimer(self)
        self.dig_timer.setSingleShot(True)
        self.dig_timer.timeout.connect(self._request_finish)

    @property
    def active(self):
        return self.phase is not None

    @property
    def on_cooldown(self):
        return self.clock() < self.cooldown_until

    def paw_anchor(self):
        ratio = self.ctx.hunt_paw_x_ratio
        if self.pet.current_animation_node() == N.START_DIG:
            player = self.pet.animation_player
            count = len(getattr(player, "frames", ())) or 5
            index = getattr(player, "current_frame_index", 0)
            ratio += .10 * (1 - min(1, index / max(1, count - 1)))
        if not self.pet.animation_player.facing_right:
            ratio = 1 - ratio
        return (round(self.pet.x() + self.pet.width() * ratio),
                round(self.pet.y() + self.pet.height() * self.ctx.hunt_paw_y_ratio))

    def plan(self, target, start_x=None):
        """Use the same landing and clearance checks before approach and takeoff."""
        screen = self.pet.get_current_screen_rect()
        if (self.on_cooldown or not screen.contains(target)
                or not self.ai._cursor_is_reachable_in_y_relaxed(target)):
            return None
        start_x = self.pet.x() if start_x is None else start_x
        facing = target.x() >= start_x + self.pet.width() // 2
        ratio = self.ctx.hunt_paw_x_ratio if facing else 1 - self.ctx.hunt_paw_x_ratio
        landing_x, _ = self.pet.clamp_position(round(target.x() - self.pet.width() * ratio), self.pet.ground_y)
        if abs(landing_x - start_x) > self.ctx.hunt_jump_max_distance:
            return None
        paw_x = round(landing_x + self.pet.width() * ratio)
        paw_y = round(self.pet.ground_y + self.pet.height() * self.ctx.hunt_paw_y_ratio)
        if ((target.x() - paw_x) ** 2 + (target.y() - paw_y) ** 2
                > self.ctx.hunt_capture_radius ** 2):
            return None
        height = max(self.ctx.hunt_jump_height,
                     min(140, self.pet.ground_y + self.pet.height() - target.y() + 35))
        trajectory = JumpTrajectory(start_x, self.pet.ground_y, landing_x,
                                    self.pet.ground_y, height)
        if self.controller.surfaces.enabled:
            foot_path = JumpTrajectory(start_x, self.pet.ground_y + self.pet.height(),
                                      landing_x, self.pet.ground_y + self.pet.height(), height)
            if not self.controller.surfaces.clear_jump(foot_path):
                return None
        return trajectory, facing

    def start(self):
        plan = self.plan(QCursor.pos())
        if plan is None:
            return False
        self.trajectory, facing = plan
        self.pet.set_facing_right(facing)
        self.start_x = self.trajectory.start_x
        self.landing_x = self.trajectory.end_x
        self.height = self.trajectory.height
        self.phase = "jump_transition"
        self.finish_pending = False
        self.captured = False
        self.ctx.is_hunt_cursor = True
        self.pet.play_node(N.JUMP, replace=True, force_restart=True)
        return self.active  # A missing clip may synchronously cancel the hunt.

    def update(self):
        if self.phase == "jump_transition" and self.pet.current_animation_node() == N.JUMP:
            self.phase = "jump"
            self.jump_started = self.clock()
            player = self.pet.animation_player
            self.jump_duration = (player.duration_ms() if hasattr(player, "duration_ms")
                                  else self.ctx.hunt_jump_duration_ms) / 1000
        if self.phase == "jump":
            progress = (self.clock() - self.jump_started) / self.jump_duration
            # Frames 0–1 are wind-up, 2–6 are flight, 7–10 are landing.
            t = flight_progress(progress)
            x, y = self.trajectory.position(t)
            x, y = round(x), round(y)
            x, y = self.pet.clamp_position(x, y)
            self.pet.move(x, y)
        elif self.phase == "dig_transition" and self.pet.current_animation_node() == N.DIG:
            self.phase = "dig"
            self.dig_timer.start(self.ctx.hunt_dig_duration_ms)

    def on_animation_finished(self, node):
        if node == N.JUMP and self.phase in {"jump", "jump_transition"}:
            self.pet.move(self.landing_x, self.pet.ground_y)
            self.phase = "dig_transition"
            self.controller._set_logical_state(PetState.DIG)
            self.pet.play_node(N.DIG, replace=True, force_restart=True)
            if not self.active:
                return
            anchor = self.paw_anchor()
            cursor = QCursor.pos()
            if ((cursor.x() - anchor[0]) ** 2 + (cursor.y() - anchor[1]) ** 2
                    > self.ctx.hunt_capture_radius ** 2):
                return  # The mouse escaped during flight; don't pull it back.
            self.captured = True
            self.holding = True
            self.ai._cursor_resist_velocity_x = 0.0
            self.ai._cursor_resist_velocity_y = 0.0
            QCursor.setPos(*anchor)
            self.release_timer.start(self.ctx.hunt_cursor_hold_ms)
            if self.ctx.swat_cursor_resist_enabled:
                self.ai.cursor_resist_timer.start(self.ctx.swat_cursor_resist_interval_ms)
        elif node == N.END_DIG and self.phase == "dig_end":
            self.cancel()
            self.controller.start_idle()

    def _request_finish(self):
        if self.phase == "dig":
            self.finish_pending = True

    def on_animation_loop_finished(self, node):
        if node == N.DIG and self.phase == "dig" and self.finish_pending:
            self.phase = "dig_end"
            self.pet.play_node(N.END_DIG, replace=True, force_restart=True)

    def release(self):
        self.release_timer.stop()
        if self.holding:
            self.ai.cursor_resist_timer.stop()
            self.ai._cursor_resist_velocity_x = 0.0
            self.ai._cursor_resist_velocity_y = 0.0
        self.holding = False

    def cancel(self, preserve_position=False):
        if self.captured or self.phase == "dig_end":
            self.cooldown_until = self.clock() + self.ctx.hunt_cooldown_seconds
        self.release()
        self.dig_timer.stop()
        if self.active:
            if self.phase in {"jump", "jump_transition"} and not preserve_position:
                self.pet.move(self.pet.x(), self.pet.ground_y)
            self.ctx.is_hunt_cursor = False
        self.phase = None
        self.captured = False
        self.finish_pending = False
