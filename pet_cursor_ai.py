import random

from PyQt6.QtCore import QObject, QTimer, QPoint
from PyQt6.QtGui import QCursor

from animation_node import AnimationNode
from interaction_mode import InteractionMode
from pet_state import PetState


class PetCursorAI(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx

        self.cursor_check_timer = QTimer(self)
        self.cursor_check_timer.timeout.connect(self.check_cursor_proximity)

        self.swat_timer = QTimer(self)
        self.swat_timer.setSingleShot(True)
        self.swat_timer.timeout.connect(self.finish_cursor_swat_due_to_timeout)

        self.swat_prepare_timer = QTimer(self)
        self.swat_prepare_timer.setSingleShot(True)
        self.swat_prepare_timer.timeout.connect(self._finish_waiting_and_start_swat)

        self.post_swat_caution_timer = QTimer(self)
        self.post_swat_caution_timer.setSingleShot(True)
        self.post_swat_caution_timer.timeout.connect(self.finish_post_swat_caution)

        self.cursor_resist_timer = QTimer(self)
        self.cursor_resist_timer.timeout.connect(self.apply_swat_cursor_resistance)

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        self._rear_startle_latched = False
        self._rear_startle_pending_swat = False
        self._rear_zone_prev = False

    # -------------------------
    # Lifecycle
    # -------------------------

    def start(self):
        self.cursor_check_timer.start(self.ctx.cursor_check_interval_ms)

    def stop(self):
        self.cursor_check_timer.stop()
        self.swat_timer.stop()
        self.swat_prepare_timer.stop()
        self.post_swat_caution_timer.stop()
        self.cursor_resist_timer.stop()

    def cancel(self):
        self.ctx.is_hunting_cursor = False
        self.ctx.is_waiting_to_swat = False
        self.ctx.is_swatting_cursor = False

        self.swat_timer.stop()
        self.swat_prepare_timer.stop()
        self.cursor_resist_timer.stop()

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        self._rear_startle_latched = False
        self._rear_startle_pending_swat = False
        self._rear_zone_prev = False

        self._reset_swat_encounter()

    # -------------------------
    # State helpers
    # -------------------------

    def _reset_swat_encounter(self):
        self.ctx.swat_count_in_encounter = 0

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

    def _is_hungry_for_feed(self) -> bool:
        return (
            self.controller.needs.values.satiety
            < self.ctx.food_begging_satiety_threshold
        )

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

    def _cursor_is_visible_for_hunting(self, cursor_pos: QPoint) -> bool:
        """
        Манул считает курсор видимым на всей ширине активного экрана.
        """
        screen_rect = self.pet.get_current_screen_rect()
        return screen_rect.left() <= cursor_pos.x() <= screen_rect.right()

    def _cursor_is_near_pet(self, cursor_pos: QPoint) -> bool:
        """
        Локальная near-зона только для startled / feed / близких реакций.
        Для hunting больше не используется.
        """
        pet_center_x = self.pet.x() + self.pet.width() // 2
        pet_center_y = self.pet.y() + self.pet.height() // 2

        dx = cursor_pos.x() - pet_center_x
        dy = cursor_pos.y() - pet_center_y
        distance_sq = dx * dx + dy * dy

        max_distance_sq = (
            self.ctx.cursor_hunting_distance * self.ctx.cursor_hunting_distance
        )
        return distance_sq <= max_distance_sq

    def _cursor_is_reachable_in_y_strict(self, cursor_pos: QPoint) -> bool:
        """
        Строгая зона досягаемости по высоте:
        используется для hunting, startled и входа в waiting_to_swat.

        Считаем от ground_y, а не от pet.y(), чтобы смена анимации
        меньше ломала расчёт.
        """
        foot_y = self.pet.ground_y + self.pet.height()
        min_y = self.pet.ground_y + int(self.pet.height() * 0.15)
        max_y = foot_y
        return min_y <= cursor_pos.y() <= max_y

    def _cursor_is_reachable_in_y_relaxed(self, cursor_pos: QPoint) -> bool:
        """
        Более мягкая зона по высоте:
        используется для удержания waiting_to_swat / swatting.
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

    def _should_hold_swat_without_moving(self, cursor_pos: QPoint) -> bool:
        pet_left = self.pet.x() - self.ctx.swat_reach_x
        pet_right = self.pet.x() + self.pet.width() + self.ctx.swat_reach_x

        return (
            pet_left <= cursor_pos.x() <= pet_right
            and self._cursor_is_reachable_in_y_relaxed(cursor_pos)
        )

    def _get_hunting_target_x(self, cursor_pos: QPoint) -> tuple[int, int]:
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

    def start_rear_startled_swat(self, cursor_pos: QPoint):
        self.controller._reset_motion_flags()

        self.ctx.is_hunting_cursor = False
        self.ctx.is_waiting_to_swat = False
        self.ctx.is_swatting_cursor = False

        self._rear_startle_pending_swat = True
        self._rear_startle_latched = True

        self._face_cursor(cursor_pos)
        self.controller._set_logical_state(PetState.ALERT)

        self.pet.play_sequence_nodes(
            [
                AnimationNode.STARTLED,
                AnimationNode.SWATTING,
            ],
            replace=True,
            force_restart=True,
        )

    def _activate_swat_after_startled(self):
        self._rear_startle_pending_swat = False
        self._enter_swat_mode(apply_energy_cost=True)

    # -------------------------
    # Hunting / waiting / swat
    # -------------------------

    def start_cursor_hunting(self):
        self.controller._reset_motion_flags()
        self.ctx.is_hunting_cursor = True
        self.ctx.is_waiting_to_swat = False
        self.ctx.is_swatting_cursor = False

        self.controller._set_logical_state(PetState.RUN)

        self.pet.play_node(
            AnimationNode.HUNTING,
            replace=True,
            force_restart=True,
        )

    def finish_cursor_hunting(self, go_idle=True):
        self.ctx.is_hunting_cursor = False
        self.ctx.is_waiting_to_swat = False
        self.swat_prepare_timer.stop()

        if go_idle:
            self.controller.start_idle()

    def start_waiting_to_swat(self):
        if self.ctx.is_waiting_to_swat or self.ctx.is_swatting_cursor:
            return

        self.ctx.is_hunting_cursor = False
        self.ctx.is_waiting_to_swat = True
        self.ctx.is_walking = False

        self.controller._set_logical_state(PetState.IDLE)

        self.pet.play_node(
            AnimationNode.STANDING_IDLE,
            replace=True,
            force_restart=True,
        )

        delay_ms = random.randint(
            self.ctx.swat_prepare_delay_min_ms,
            self.ctx.swat_prepare_delay_max_ms,
        )
        self.swat_prepare_timer.start(delay_ms)

    def cancel_waiting_to_swat(self, go_idle=True):
        self.ctx.is_waiting_to_swat = False
        self.swat_prepare_timer.stop()

        if go_idle:
            self.controller.start_idle()

    def _finish_waiting_and_start_swat(self):
        cursor_pos = QCursor.pos()

        if (
            self.ctx.is_waiting_to_swat
            and self._can_swat_cursor_relaxed(cursor_pos)
        ):
            self.start_cursor_swat()
        else:
            self.cancel_waiting_to_swat(go_idle=True)

    def _enter_swat_mode(self, apply_energy_cost: bool = True):
        self.ctx.is_hunting_cursor = False
        self.ctx.is_waiting_to_swat = False
        self.ctx.is_swatting_cursor = True
        self.ctx.is_walking = False

        self.swat_prepare_timer.stop()

        self.ctx.swat_count_in_encounter += 1

        if apply_energy_cost:
            self.controller.needs.apply_swat_cost()

        self.controller._set_logical_state(PetState.SWAT)

        cursor_pos = QCursor.pos()
        self.pet.set_facing_right(
            cursor_pos.x() >= self.pet.x() + self.pet.width() // 2
        )

        self.pet.play_node(
            AnimationNode.SWATTING,
            replace=True,
            force_restart=True,
        )

        self.swat_timer.stop()
        self.swat_timer.start(self.ctx.swat_timeout_ms)

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        if getattr(self.ctx, "swat_cursor_resist_enabled", False):
            self.cursor_resist_timer.start(
                self.ctx.swat_cursor_resist_interval_ms
            )

    def start_cursor_swat(self):
        self._enter_swat_mode(apply_energy_cost=True)

    def finish_cursor_swat(self, go_idle=True):
        self.ctx.is_swatting_cursor = False
        self.swat_timer.stop()
        self.cursor_resist_timer.stop()
        self._rear_startle_pending_swat = False

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        if go_idle:
            self.controller.start_idle()

    def finish_cursor_swat_due_to_timeout(self):
        if self.ctx.is_swatting_cursor:
            self._start_post_swat_caution()
            self.finish_cursor_swat(go_idle=True)

    # -------------------------
    # Swat cursor resistance
    # -------------------------

    def _get_swat_resist_anchor(self) -> tuple[float, float]:
        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            anchor_x = self.pet.x() + self.pet.width() - self.ctx.cursor_front_gap
        else:
            anchor_x = self.pet.x() + self.ctx.cursor_front_gap

        anchor_y = self.pet.y() + int(self.pet.height() * 0.70)
        return float(anchor_x), float(anchor_y)

    def apply_swat_cursor_resistance(self):
        if not self.ctx.is_swatting_cursor:
            return

        cursor_pos = QCursor.pos()
        anchor_x, anchor_y = self._get_swat_resist_anchor()

        dx = float(cursor_pos.x()) - anchor_x
        dy = float(cursor_pos.y()) - anchor_y

        distance_sq = dx * dx + dy * dy
        dead_zone = float(self.ctx.swat_cursor_dead_zone_radius)
        break_distance = float(self.ctx.swat_cursor_break_distance)

        if distance_sq >= break_distance * break_distance:
            self._cursor_resist_velocity_x *= 0.5
            self._cursor_resist_velocity_y *= 0.5
            return

        if distance_sq <= dead_zone * dead_zone:
            self._cursor_resist_velocity_x *= 0.5
            self._cursor_resist_velocity_y *= 0.5
            return

        spring_strength = self.ctx.swat_cursor_spring_strength
        damping = self.ctx.swat_cursor_damping
        max_pull = self.ctx.swat_cursor_max_pull_per_tick

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
        if (
            self.ctx.is_falling
            or self.ctx.is_dragging
            or self.ctx.is_recovering
            or self.ctx.is_cleaning
            or self.ctx.is_sleeping
            or self.ctx.is_meowing
            or self.ctx.is_menu_open
            or self.ctx.is_menu_forced_meowing
            or self.ctx.is_eating
            or self.ctx.is_pooping
            or self.ctx.is_post_pooping_zoomies
            or self.ctx.is_hiding
            or self.ctx.is_investigating_notifications
        ):
            return

        # startled -> swatting chain уже в процессе
        if self._rear_startle_pending_swat:
            if self.pet.current_animation_node() == AnimationNode.SWATTING:
                self._activate_swat_after_startled()
            return

        # startled только из sitting_idle и только при входе сзади
        if (
            self.pet.current_animation_node() == AnimationNode.SITTING_IDLE
            and not self.ctx.is_hunting_cursor
            and not self.ctx.is_waiting_to_swat
            and not self.ctx.is_swatting_cursor
        ):
            if rear_zone_entered and not self._rear_startle_latched:
                self.start_rear_startled_swat(cursor_pos)
                return

        # FEED + голод => scratching_screen вместо hunting / swat
        if self._feed_mode_active() and self._is_hungry_for_feed():
            if (
                self._cursor_is_near_pet(cursor_pos)
                and self._cursor_is_reachable_in_y_strict(cursor_pos)
            ):
                if not self.ctx.is_scratching_for_food:
                    self.controller.start_scratching_for_food()
                return
            else:
                if self.ctx.is_scratching_for_food:
                    self.controller.finish_scratching_for_food()

        # Уже swatting
        if self.ctx.is_swatting_cursor:
            if self._should_hold_swat_without_moving(cursor_pos):
                self._face_cursor(cursor_pos)

                if self.pet.current_animation_node() != AnimationNode.SWATTING:
                    self.pet.play_node(
                        AnimationNode.SWATTING,
                        replace=True,
                        force_restart=True,
                    )
                return

            if not (
                self._cursor_is_visible_for_hunting(cursor_pos)
                and self._cursor_is_reachable_in_y_relaxed(cursor_pos)
            ):
                self._reset_swat_encounter()
                self.finish_cursor_swat(go_idle=True)
            return

        # Уже ждём swat
        if self.ctx.is_waiting_to_swat:
            if self._can_swat_cursor_relaxed(cursor_pos):
                self._face_cursor(cursor_pos)
            else:
                self.cancel_waiting_to_swat(go_idle=True)
            return

        # Если курсор в полной досягаемости — запускаем ожидание swat
        if self._can_swat_cursor_strict(cursor_pos):
            self._face_cursor(cursor_pos)
            self.start_waiting_to_swat()
            return

        # Hunting:
        # курсор видим на любом расстоянии по X в пределах экрана,
        # находится по высоте в зоне досягаемости,
        # не двигался 10 секунд,
        # но ещё не в зоне swat.
        if (
            self._cursor_is_visible_for_hunting(cursor_pos)
            and self._cursor_is_reachable_in_y_strict(cursor_pos)
            and not self._can_swat_cursor_strict(cursor_pos)
            and self._cursor_is_stationary_long_enough_for_hunt()
        ):
            if not self.ctx.is_hunting_cursor:
                self.start_cursor_hunting()
            return

        # Если hunting уже шёл, но условия исчезли — прекращаем
        if self.ctx.is_hunting_cursor:
            if (
                not self._cursor_is_visible_for_hunting(cursor_pos)
                or not self._cursor_is_reachable_in_y_strict(cursor_pos)
                or not self._cursor_is_stationary_long_enough_for_hunt()
            ):
                self.finish_cursor_hunting(go_idle=True)

    # -------------------------
    # Movement hook
    # -------------------------

    def process_chase_step(self) -> bool:
        """
        Имя оставлено ради совместимости с controller,
        но внутри теперь hunting / waiting / swat pipeline.
        """
        if self.ctx.is_menu_open or self.ctx.is_menu_forced_meowing:
            return False

        if self.ctx.is_hiding:
            return False

        if self.ctx.is_pooping or self.ctx.is_post_pooping_zoomies:
            return False

        if self.ctx.is_eating:
            return False

        if self.ctx.is_swatting_cursor:
            return True

        if self.ctx.is_waiting_to_swat:
            return True

        if self.ctx.is_hunting_cursor and not self.ctx.is_dragging:
            cursor_pos = QCursor.pos()

            if not self._cursor_is_reachable_in_y_strict(cursor_pos):
                self.finish_cursor_hunting(go_idle=True)
                return True

            # Если курсор вошёл в full reach — останавливаемся и ждём swat
            if self._can_swat_cursor_strict(cursor_pos):
                self._face_cursor(cursor_pos)
                self._stop_hunting_motion()
                self.start_waiting_to_swat()
                return True

            current_x = self.pet.x()
            target_x, direction = self._get_hunting_target_x(cursor_pos)

            self.pet.set_facing_right(direction == 1)

            if self.pet.current_animation_node() != AnimationNode.HUNTING:
                self.pet.play_node(
                    AnimationNode.HUNTING,
                    replace=True,
                    force_restart=True,
                )

            if target_x == current_x:
                return True

            step = self.ctx.cursor_hunting_speed * direction
            new_x = current_x + step

            if direction == 1:
                new_x = min(new_x, target_x)
            else:
                new_x = max(new_x, target_x)

            new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
            self.pet.move(new_x, new_y)
            return True

        return False

    def _stop_hunting_motion(self):
        self.ctx.is_walking = False