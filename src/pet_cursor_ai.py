import random

from PyQt6.QtCore import QObject, QTimer, QPoint
from PyQt6.QtGui import QCursor

from animation_node import AnimationNode
from interaction_mode import InteractionMode
from pet_state import PetState
from cursor_jump import CursorJump


# Contact points on the moving front paw in the imported 112 x 80 SWAT canvas.
# Pixel centers are scaled with the displayed frame, then mirrored if needed.
SWAT_PAW_POINTS = (
    (64, 75), (67, 65), (86, 31), (86, 31), (86, 31), (86, 33),
    (86, 45), (86, 46), (84, 40), (86, 31), (67, 65),
)


class PetCursorAI(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx

        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self.check_cursor_proximity)

        self.swat_prepare_timer = QTimer(self)
        self.swat_prepare_timer.setSingleShot(True)
        self.swat_prepare_timer.timeout.connect(self._finish_wait_and_start_swat)

        self.post_swat_caution_timer = QTimer(self)
        self.post_swat_caution_timer.setSingleShot(True)
        self.post_swat_caution_timer.timeout.connect(self.finish_post_swat_caution)

        self.cursor_resist_timer = QTimer(self)
        self.cursor_resist_timer.timeout.connect(self.apply_swat_cursor_resistance)

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0
        self._swat_previous_anchor = None

        self._rear_startle_latched = False
        self._rear_startle_pending_swat = False
        self._rear_zone_prev = False

        self._hunt_exit_target = None
        self._hunt_exit_started = False
        self._hunt_retry_until = 0.0
        self.jump = CursorJump(self)

    # -------------------------
    # Lifecycle
    # -------------------------

    def start(self):
        self.cursor_check_timer.start(self.ctx.cursor_check_interval_ms)

    def stop(self):
        self.jump.cancel()
        self.cursor_check_timer.stop()
        self.swat_prepare_timer.stop()
        self.post_swat_caution_timer.stop()
        self.cursor_resist_timer.stop()

    def cancel(self):
        self._swat_previous_anchor = None
        self.jump.cancel()
        self._hunt_exit_target = None
        self._hunt_exit_started = False
        self.ctx.is_hunt_cursor = False
        self.ctx.is_wait_to_swat = False
        self.ctx.is_swat_cursor = False

        self.swat_prepare_timer.stop()
        self.cursor_resist_timer.stop()

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        self._rear_startle_latched = False
        self._rear_startle_pending_swat = False
        self._rear_zone_prev = False

        self._reset_swat_encounter()

    def is_busy(self):
        return (self.ctx.is_hunt_cursor or self.ctx.is_wait_to_swat
                or self.ctx.is_swat_cursor or self._rear_startle_pending_swat)

    # -------------------------
    # State helpers
    # -------------------------

    def _reset_swat_encounter(self):
        self.ctx.swat_count_in_encounter = 0

    def _stop_cursor_play(self, go_idle: bool = True):
        """
        Полностью сбрасывает sneak / wait / обычный swat.
        """
        if self.jump.active:
            self.jump.cancel()
            if go_idle:
                self.controller.start_idle()
            return
        if go_idle and self.ctx.is_hunt_cursor:
            self._request_hunt_exit("idle")
            return
        self.ctx.is_hunt_cursor = False
        self.ctx.is_wait_to_swat = False
        self.ctx.is_swat_cursor = False

        self.swat_prepare_timer.stop()
        self.cursor_resist_timer.stop()

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        self._rear_startle_pending_swat = False
        self._reset_swat_encounter()

        if go_idle:
            self.controller.start_idle()

    def _start_post_swat_caution(self):
        self.ctx.is_post_swat_cautious = True
        self.post_swat_caution_timer.start(self.ctx.post_swat_caution_ms)

    def finish_post_swat_caution(self):
        self.ctx.is_post_swat_cautious = False

    def _feed_mode_active(self) -> bool:
        try:
            return self.pet.cursors.current_mode() == InteractionMode.FEED
        except Exception:
            return False

    def wants_food(self, cursor_pos):
        return (self._feed_mode_active() and self.controller.can_feed()
                and self._cursor_is_near_pet(cursor_pos))

    # -------------------------
    # Cursor motion / geometry helpers
    # -------------------------

    def _update_cursor_motion_state(self):
        cursor_pos = QCursor.pos()

        if self.ctx.last_cursor_pos is None:
            self.ctx.last_cursor_pos = cursor_pos
            self.ctx.cursor_still_ticks = 0
            self.ctx.cursor_stationary_ms = 0
            return cursor_pos

        dx = cursor_pos.x() - self.ctx.last_cursor_pos.x()
        dy = cursor_pos.y() - self.ctx.last_cursor_pos.y()
        distance_sq = dx * dx + dy * dy

        threshold_sq = (
            self.ctx.cursor_stationary_threshold
            * self.ctx.cursor_stationary_threshold
        )

        if distance_sq <= threshold_sq:
            self.ctx.cursor_still_ticks += 1
            self.ctx.cursor_stationary_ms += self.ctx.cursor_check_interval_ms
        else:
            self.ctx.cursor_still_ticks = 0
            self.ctx.cursor_stationary_ms = 0

        self.ctx.last_cursor_pos = cursor_pos
        return cursor_pos

    def _cursor_is_stationary_long_enough_for_hunt(self) -> bool:
        return self.ctx.cursor_stationary_ms >= self.ctx.cursor_hunt_start_after_ms

    def _cursor_is_visible_for_hunt(self, cursor_pos: QPoint) -> bool:
        """
        Цель должна находиться внутри активного экрана по обеим координатам.
        """
        screen_rect = self.pet.get_current_screen_rect()
        return screen_rect.contains(cursor_pos)

    def _cursor_is_near_pet(self, cursor_pos: QPoint) -> bool:
        """
        Локальная near-зона только для startle / feed / близких реакций.
        Для sneak не используется.
        """
        pet_center_x = self.pet.x() + self.pet.width() // 2
        pet_center_y = self.pet.y() + self.pet.height() // 2

        dx = cursor_pos.x() - pet_center_x
        dy = cursor_pos.y() - pet_center_y
        distance_sq = dx * dx + dy * dy

        max_distance_sq = (
            self.ctx.cursor_hunt_distance * self.ctx.cursor_hunt_distance
        )
        return distance_sq <= max_distance_sq

    def _cursor_is_reachable_in_y_strict(self, cursor_pos: QPoint) -> bool:
        """
        Строгая зона досягаемости по высоте:
        - sneak
        - startle
        - вход в wait_to_swat
        """
        foot_y = self.pet.ground_y + self.pet.height()
        min_y = self.pet.ground_y + int(self.pet.height() * 0.15)
        max_y = foot_y
        return min_y <= cursor_pos.y() <= max_y

    def _cursor_is_reachable_in_y_relaxed(self, cursor_pos: QPoint) -> bool:
        """
        Более мягкая зона по высоте:
        - удержание wait_to_swat
        - удержание swat
        """
        foot_y = self.pet.ground_y + self.pet.height()
        min_y = self.pet.ground_y + int(self.pet.height() * 0.05)
        max_y = foot_y + 10
        return min_y <= cursor_pos.y() <= max_y

    def _face_cursor(self, cursor_pos: QPoint):
        desired_facing_right = cursor_pos.x() >= self.pet.x() + self.pet.width() // 2
        if self.pet.animation_player.facing_right != desired_facing_right:
            self.pet.set_facing_right(desired_facing_right)

    def _cursor_in_swat_x_reach(self, cursor_pos: QPoint) -> bool:
        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            front_x = self.pet.x() + self.pet.width() - self.ctx.cursor_front_gap
        else:
            front_x = self.pet.x() + self.ctx.cursor_front_gap

        return abs(cursor_pos.x() - front_x) <= self.ctx.swat_reach_x

    def _can_swat_cursor_strict(self, cursor_pos: QPoint) -> bool:
        return (
            self._cursor_in_swat_x_reach(cursor_pos)
            and self._cursor_is_reachable_in_y_strict(cursor_pos)
        )

    def _can_swat_cursor_relaxed(self, cursor_pos: QPoint) -> bool:
        return (
            self._cursor_in_swat_x_reach(cursor_pos)
            and self._cursor_is_reachable_in_y_relaxed(cursor_pos)
        )

    def _get_hunt_target_x(self, cursor_pos: QPoint) -> tuple[int, int]:
        pet_center_x = self.pet.x() + self.pet.width() // 2

        if cursor_pos.x() < pet_center_x - self.ctx.cursor_dead_zone:
            direction = -1
        elif cursor_pos.x() > pet_center_x + self.ctx.cursor_dead_zone:
            direction = 1
        else:
            direction = 1 if self.pet.animation_player.facing_right else -1

        if direction == 1:
            target_x = (cursor_pos.x() - (self.pet.width() - self.ctx.cursor_front_gap)
                        - self.ctx.hunt_standoff_distance)
        else:
            target_x = cursor_pos.x() - self.ctx.cursor_front_gap + self.ctx.hunt_standoff_distance

        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)
        return target_x, direction

    # -------------------------
    # Startled from rear
    # -------------------------

    def _cursor_is_behind_pet(self, cursor_pos: QPoint) -> bool:
        pet_left = self.pet.x()
        pet_right = self.pet.x() + self.pet.width()

        if not self._cursor_is_reachable_in_y_strict(cursor_pos):
            return False

        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            rear_limit_x = pet_left + int(self.pet.width() * 0.25)
            return cursor_pos.x() <= rear_limit_x
        else:
            rear_limit_x = pet_right - int(self.pet.width() * 0.25)
            return cursor_pos.x() >= rear_limit_x

    def start_rear_startle_swat(self, cursor_pos: QPoint):
        if self.jump.on_cooldown:
            return
        self.controller._reset_motion_flags()

        self.ctx.is_hunt_cursor = False
        self.ctx.is_wait_to_swat = False
        self.ctx.is_swat_cursor = False

        self._rear_startle_pending_swat = True
        self._rear_startle_latched = True

        self._face_cursor(cursor_pos)
        self.controller._set_logical_state(PetState.ALERT)

        self.pet.play_sequence_nodes(
            [
                AnimationNode.STARTLE,
                AnimationNode.SWAT,
            ],
            replace=True,
            force_restart=True,
        )

    def _activate_swat_after_startle(self):
        self._rear_startle_pending_swat = False

        self._enter_swat_mode()

    # -------------------------
    # Hunting / wait / swat
    # -------------------------

    def _can_hunt_target(self, cursor_pos):
        if (self.jump.clock() < self._hunt_retry_until
                or not self._cursor_is_visible_for_hunt(cursor_pos)
                or not self._cursor_is_reachable_in_y_strict(cursor_pos)):
            return False
        launch_x, _ = self._get_hunt_target_x(cursor_pos)
        return self.jump.plan(cursor_pos, start_x=launch_x) is not None

    def _defer_hunt(self):
        self._hunt_retry_until = self.jump.clock() + self.ctx.hunt_retry_seconds
        self.ctx.cursor_stationary_ms = 0
        self.ctx.cursor_still_ticks = 0

    def start_cursor_hunt(self):
        if not self._can_hunt_target(QCursor.pos()):
            return False
        self.controller._reset_motion_flags()
        self.ctx.is_hunt_cursor = True
        self.ctx.is_wait_to_swat = False
        self.ctx.is_swat_cursor = False

        self.controller._set_logical_state(PetState.RUN)

        self.pet.play_node(
            AnimationNode.SNEAK,
            replace=True,
            force_restart=True,
        )

        return self.ctx.is_hunt_cursor

    def finish_cursor_hunt(self, go_idle=True):
        if go_idle:
            self._request_hunt_exit("idle")
        else:
            self.ctx.is_hunt_cursor = False
            self._hunt_exit_target = None
            self._hunt_exit_started = False

    def _request_hunt_exit(self, target):
        if not self.ctx.is_hunt_cursor:
            return
        if target == "idle" and self._hunt_exit_target != "idle":
            self._defer_hunt()
        self._hunt_exit_target = target
        self._stop_hunt_motion()
        if target == "jump":
            # Once we reach the target, another partial walk cycle slides in place.
            self._begin_hunt_exit()

    def _begin_hunt_exit(self):
        if (not self.ctx.is_hunt_cursor or self._hunt_exit_target is None
                or self._hunt_exit_started):
            return
        self._hunt_exit_started = True
        self.pet.play_node(AnimationNode.END_SNEAK, replace=True, force_restart=True)

    def on_animation_loop_finished(self, node):
        self.jump.on_animation_loop_finished(node)
        if node == AnimationNode.SNEAK:
            self._begin_hunt_exit()

    def on_animation_finished(self, node):
        self.jump.on_animation_finished(node)
        if node == AnimationNode.SWAT and (self.ctx.is_swat_cursor or self._rear_startle_pending_swat):
            self.finish_cursor_swat_action()
            return
        if (node != AnimationNode.END_SNEAK or not self._hunt_exit_started
                or not self.ctx.is_hunt_cursor):
            return
        target = self._hunt_exit_target
        self._hunt_exit_target = None
        self._hunt_exit_started = False
        self.ctx.is_hunt_cursor = False
        if target == "jump":
            if not self.jump.start():
                self._defer_hunt()
                self.controller.start_idle()
        elif target == "swat":
            self.start_wait_to_swat()
        else:
            self.controller.start_idle()

    def start_wait_to_swat(self):
        if self.jump.on_cooldown or self.ctx.is_post_swat_cautious:
            return
        if self.ctx.is_hunt_cursor:
            self._request_hunt_exit("swat")
            return
        if self.ctx.is_wait_to_swat or self.ctx.is_swat_cursor:
            return

        self.controller._reset_motion_flags()

        self.ctx.is_hunt_cursor = False
        self.ctx.is_wait_to_swat = True
        self.ctx.is_walk = False

        self.controller._set_logical_state(PetState.IDLE)

        self.pet.play_node(
            AnimationNode.STAND_IDLE,
            replace=True,
            force_restart=True,
        )

        if not self.ctx.is_wait_to_swat:
            return

        delay_ms = random.randint(
            self.ctx.swat_prepare_delay_min_ms,
            self.ctx.swat_prepare_delay_max_ms,
        )
        self.swat_prepare_timer.start(delay_ms)

    def cancel_wait_to_swat(self, go_idle=True):
        self.ctx.is_wait_to_swat = False
        self.swat_prepare_timer.stop()

        if go_idle:
            self.controller.start_idle()

    def _finish_wait_and_start_swat(self):
        if not self.ctx.is_wait_to_swat:
            return
        cursor_pos = QCursor.pos()

        if (
            self.ctx.is_wait_to_swat
            and self._can_swat_cursor_relaxed(cursor_pos)
        ):
            self.start_cursor_swat()
        else:
            self.cancel_wait_to_swat(go_idle=True)

    def _enter_swat_mode(self):
        """One hit with the same paw capture for direct and startled reactions."""
        if self.jump.on_cooldown or self.ctx.is_post_swat_cautious or self.ctx.is_swat_cursor:
            return
        self._swat_previous_anchor = None
        self.ctx.is_hunt_cursor = False
        self.ctx.is_wait_to_swat = False
        self.ctx.is_swat_cursor = True
        self.ctx.is_walk = False

        self.swat_prepare_timer.stop()

        self.ctx.swat_count_in_encounter += 1

        self.controller._set_logical_state(PetState.SWAT)

        cursor_pos = QCursor.pos()
        self.pet.set_facing_right(
            cursor_pos.x() >= self.pet.x() + self.pet.width() // 2
        )

        # The rear-startle sequence may already have entered SWAT.
        if self.pet.current_animation_node() != AnimationNode.SWAT:
            self.pet.play_node(
                AnimationNode.SWAT,
                replace=True,
                force_restart=True,
            )

        if not self.ctx.is_swat_cursor:
            return


        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        if self.ctx.swat_cursor_resist_enabled:
            self.cursor_resist_timer.start(
                self.ctx.swat_cursor_resist_interval_ms
            )
        else:
            self.cursor_resist_timer.stop()

    def start_cursor_swat(self):
        self._enter_swat_mode()

    def finish_cursor_swat(self, go_idle=True):
        self._swat_previous_anchor = None
        self.ctx.is_swat_cursor = False
        self.cursor_resist_timer.stop()
        self._rear_startle_pending_swat = False

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        if go_idle:
            self.controller.start_idle()

    def finish_cursor_swat_action(self):
        if self.ctx.is_swat_cursor or self._rear_startle_pending_swat:
            self._start_post_swat_caution()
            self.finish_cursor_swat(go_idle=True)

    # -------------------------
    # Swat cursor resistance
    # -------------------------

    def _get_swat_resist_anchor(self) -> tuple[float, float]:
        player = self.pet.animation_player
        index = min(max(getattr(player, 'current_frame_index', 0), 0), len(SWAT_PAW_POINTS) - 1)
        x, y = SWAT_PAW_POINTS[index]
        x_ratio = (x + .5) / 112
        if not player.facing_right:
            x_ratio = 1 - x_ratio
        return (self.pet.x() + self.pet.width() * x_ratio,
                self.pet.y() + self.pet.height() * (y + .5) / 80)

    def apply_swat_cursor_resistance(self):
        if not self.ctx.is_swat_cursor and not self.jump.holding:
            return

        if not self.jump.holding and self.pet.current_animation_node() != AnimationNode.SWAT:
            return  # Do not pull toward SWAT coordinates during a pose transition.

        cursor_pos = QCursor.pos()
        anchor_x, anchor_y = (self.jump.paw_anchor() if self.jump.holding
                              else self._get_swat_resist_anchor())

        dx = float(cursor_pos.x()) - anchor_x
        dy = float(cursor_pos.y()) - anchor_y

        distance_sq = dx * dx + dy * dy
        dead_zone = float(self.ctx.swat_cursor_dead_zone_radius if self.jump.holding
                          else self.ctx.swat_paw_dead_zone_radius)
        break_distance = float(self.ctx.swat_cursor_break_distance if self.jump.holding
                               else self.ctx.swat_paw_break_distance)

        if not self.jump.holding:
            previous = self._swat_previous_anchor
            self._swat_previous_anchor = (anchor_x, anchor_y)
            if previous is not None and previous != (anchor_x, anchor_y):
                old_dx, old_dy = cursor_pos.x() - previous[0], cursor_pos.y() - previous[1]
                if old_dx * old_dx + old_dy * old_dy < break_distance * break_distance:
                    # Carry the grabbed cursor with the animated paw; spring lag
                    # would otherwise leave it behind on the fast raised frames.
                    cursor_pos = QPoint(round(cursor_pos.x() + anchor_x - previous[0]),
                                        round(cursor_pos.y() + anchor_y - previous[1]))
                    QCursor.setPos(cursor_pos.x(), cursor_pos.y())
                    dx, dy = cursor_pos.x() - anchor_x, cursor_pos.y() - anchor_y
                    distance_sq = dx * dx + dy * dy
                    self._cursor_resist_velocity_x = 0.0
                    self._cursor_resist_velocity_y = 0.0

        if distance_sq >= break_distance * break_distance:
            self._cursor_resist_velocity_x *= 0.5
            self._cursor_resist_velocity_y *= 0.5
            return

        if distance_sq <= dead_zone * dead_zone:
            self._cursor_resist_velocity_x *= 0.5
            self._cursor_resist_velocity_y *= 0.5
            return

        spring_strength = (self.ctx.swat_cursor_spring_strength if self.jump.holding
                           else self.ctx.swat_paw_spring_strength)
        damping = self.ctx.swat_cursor_damping
        max_pull = (self.ctx.swat_cursor_max_pull_per_tick if self.jump.holding
                    else self.ctx.swat_paw_max_pull_per_tick)

        force_x = -dx * spring_strength
        force_y = -dy * spring_strength

        self._cursor_resist_velocity_x = (
            (self._cursor_resist_velocity_x + force_x) * damping
        )
        self._cursor_resist_velocity_y = (
            (self._cursor_resist_velocity_y + force_y) * damping
        )

        move_x = max(-max_pull, min(max_pull, self._cursor_resist_velocity_x))
        move_y = max(-max_pull, min(max_pull, self._cursor_resist_velocity_y))

        if abs(move_x) < 0.5 and abs(move_y) < 0.5:
            return

        new_x = int(cursor_pos.x() + move_x)
        new_y = int(cursor_pos.y() + move_y)

        if new_x != cursor_pos.x() or new_y != cursor_pos.y():
            QCursor.setPos(new_x, new_y)

    # -------------------------
    # Periodic AI tick
    # -------------------------

    def check_cursor_proximity(self):
        cursor_pos = self._update_cursor_motion_state()

        rear_zone_now = (
            self._cursor_is_near_pet(cursor_pos)
            and self._cursor_is_behind_pet(cursor_pos)
        )
        rear_zone_entered = rear_zone_now and not self._rear_zone_prev
        self._rear_zone_prev = rear_zone_now

        if not self._cursor_is_near_pet(cursor_pos):
            self._rear_startle_latched = False

        # Жёсткие блокировки
        if self.controller.interaction_locked:
            return

        active = self.controller.behaviors.active
        # A nearby food cursor starts a persistent request. An existing request
        # monitors its own exit conditions and must not restart every AI tick.
        if self._feed_mode_active():
            if self.controller.behaviors.blocks_cursor and active.id != 'beg_food':
                return
            if self.wants_food(cursor_pos):
                self.controller.start_behavior('food_beg')
                return
            if self.jump.active:
                return
            if self.is_busy():
                self._stop_cursor_play(go_idle=True)
            return

        if self.controller.behaviors.blocks_cursor:
            return

        if self.jump.on_cooldown or self.ctx.is_post_swat_cautious:
            return

        if self.jump.active:
            return

        if self._hunt_exit_target is not None:
            return

        # startle -> swat chain уже в процессе
        if self._rear_startle_pending_swat:
            if self.pet.current_animation_node() == AnimationNode.SWAT:
                self._activate_swat_after_startle()
            return

        if self.ctx.is_hunt_cursor:
            if (not self._can_hunt_target(cursor_pos)
                    or not self._cursor_is_stationary_long_enough_for_hunt()):
                self.finish_cursor_hunt(go_idle=True)
            return

        # startle только из sit_idle и только при входе сзади
        if (
            self.pet.current_animation_node() == AnimationNode.SIT_IDLE
            and not self.ctx.is_hunt_cursor
            and not self.ctx.is_wait_to_swat
            and not self.ctx.is_swat_cursor
        ):
            if rear_zone_entered and not self._rear_startle_latched:
                self.start_rear_startle_swat(cursor_pos)
                return

        # Уже swat
        if self.ctx.is_swat_cursor:
            # Finish the single clip even if the cursor escapes during the hit.
            return

        # Уже ждём swat
        if self.ctx.is_wait_to_swat:
            if self._can_swat_cursor_relaxed(cursor_pos):
                self._face_cursor(cursor_pos)
            else:
                self.cancel_wait_to_swat(go_idle=True)
            return

        # Если курсор в полной досягаемости — запускаем ожидание swat
        if self._can_swat_cursor_strict(cursor_pos):
            self._face_cursor(cursor_pos)
            self.start_wait_to_swat()
            return

        # Hunting:
        # курсор видим на любом расстоянии по X в пределах экрана,
        # находится по высоте в зоне досягаемости,
        # не двигался 10 секунд,
        # но ещё не в зоне swat.
        if (
            self._cursor_is_visible_for_hunt(cursor_pos)
            and self._cursor_is_reachable_in_y_strict(cursor_pos)
            and not self._can_swat_cursor_strict(cursor_pos)
            and self._cursor_is_stationary_long_enough_for_hunt()
        ):
            if not self.ctx.is_hunt_cursor:
                self.start_cursor_hunt()
            return

    # -------------------------
    # Movement hook
    # -------------------------

    def process_chase_step(self) -> bool:
        """
        Имя оставлено ради совместимости с controller,
        Handles approach, jump and stationary dig; also legacy swat.
        """
        if self.jump.active:
            self.jump.update()
            return True

        if self.controller.interaction_locked or self.controller.behaviors.blocks_cursor:
            return False

        if self._rear_startle_pending_swat:
            if self.pet.current_animation_node() == AnimationNode.SWAT:
                self._activate_swat_after_startle()
            return True

        if self._hunt_exit_target is not None:
            return True  # Keep still while finishing the cycle and standing up.

        if self.ctx.is_swat_cursor:
            return True

        if self.ctx.is_wait_to_swat:
            return True

        if self.ctx.is_hunt_cursor and not self.ctx.is_drag:
            cursor_pos = QCursor.pos()

            if (not self._cursor_is_visible_for_hunt(cursor_pos)
                    or not self._cursor_is_reachable_in_y_strict(cursor_pos)):
                self.finish_cursor_hunt(go_idle=True)
                return True

            current_x = self.pet.x()
            target_x, direction = self._get_hunt_target_x(cursor_pos)

            self.pet.set_facing_right(direction == 1)

            # The initial request owns the transition. Restarting it every
            # movement tick prevents longer standing-up clips from finishing.
            if self.pet.current_animation_node() != AnimationNode.SNEAK:
                return True

            if target_x == current_x:
                self._request_hunt_exit("jump")
                return True

            move_direction = 1 if target_x > current_x else -1
            step = self.ctx.cursor_hunt_speed * move_direction
            new_x = current_x + step

            if move_direction == 1:
                new_x = min(new_x, target_x)
            else:
                new_x = max(new_x, target_x)

            new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
            self.pet.move(new_x, new_y)
            if new_x == target_x:
                self._request_hunt_exit("jump")
            return True

        return False

    def _stop_hunt_motion(self):
        self.ctx.is_walk = False
