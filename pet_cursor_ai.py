import random

from PyQt6.QtCore import QObject, QTimer, QPoint
from PyQt6.QtGui import QCursor

from animation_node import AnimationNode
from pet_state import PetState
from interaction_mode import InteractionMode


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

        self.swat_timer = QTimer(self)
        self.swat_timer.setSingleShot(True)
        self.swat_timer.timeout.connect(self.finish_cursor_swat_due_to_timeout)

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
        self.cursor_check_timer.start(120)

    def stop(self):
        self.cursor_check_timer.stop()
        self.chase_timer.stop()
        self.cursor_chase_cooldown_timer.stop()
        self.swat_timer.stop()
        self.post_swat_caution_timer.stop()
        self.cursor_resist_timer.stop()

    def cancel(self):
        self.ctx.is_chasing_cursor = False
        self.ctx.is_swatting_cursor = False

        self.chase_timer.stop()
        self.swat_timer.stop()
        self.cursor_resist_timer.stop()

        self._cursor_resist_velocity_x = 0.0
        self._cursor_resist_velocity_y = 0.0

        self._rear_startle_latched = False
        self._rear_startle_pending_swat = False
        self._rear_zone_prev = False

        self._reset_swat_encounter()

        

    # -------------------------
    # Encounter helpers
    # -------------------------

    def _reset_swat_encounter(self):
        self.ctx.swat_count_in_encounter = 0

    def _start_post_swat_caution(self):
        self.ctx.is_post_swat_cautious = True
        self.post_swat_caution_timer.start(self.ctx.post_swat_caution_ms)

    def finish_post_swat_caution(self):
        self.ctx.is_post_swat_cautious = False

    def _current_chase_trigger_chance(self) -> float:
        if self.ctx.is_post_swat_cautious:
            return self.ctx.post_swat_trigger_chance
        return self.ctx.cursor_chase_trigger_chance

    def _feed_mode_active(self) -> bool:
        try:
            return self.pet.cursors.current_mode() == InteractionMode.FEED
        except Exception:
            return False

    def _is_hungry_for_feed(self) -> bool:
        return self.controller.needs.values.satiety < self.ctx.food_begging_satiety_threshold

    def _cursor_is_behind_pet(self, cursor_pos: QPoint) -> bool:
        """
        Курсор считается "сзади", если он находится
        в задней четверти корпуса, а не просто где угодно
        по ту сторону центра.
        """
        pet_left = self.pet.x()
        pet_right = self.pet.x() + self.pet.width()

        if not self._cursor_is_reachable_in_y(cursor_pos):
            return False

        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            rear_limit_x = pet_left + int(self.pet.width() * 0.25)
            return cursor_pos.x() <= rear_limit_x
        else:
            rear_limit_x = pet_right - int(self.pet.width() * 0.25)
            return cursor_pos.x() >= rear_limit_x

    def start_rear_startled_swat(self, cursor_pos: QPoint):
        """
        Курсор подошёл сзади -> манул пугается, разворачивается и начинает swat.
        Анимационно запускаем sequence:
            STARTLED -> SWATTING

        Граф сам подставит промежуточный STANDING_IDLE, если нужно.
        """
        self.controller._reset_motion_flags()

        self.ctx.is_chasing_cursor = False
        self.ctx.is_swatting_cursor = False

        self._rear_startle_pending_swat = True
        self._rear_startle_latched = True

        # Сразу разворачиваемся к курсору
        self._face_cursor(cursor_pos)

        # Логически это ближе всего к alert/startled,
        # а активный swat включим, когда sequence реально дойдёт до SWATTING
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
        """
        Когда sequence реально дошла до SWATTING,
        переводим AI в полноценный swat-mode.
        """
        self._rear_startle_pending_swat = False
        self._enter_swat_mode(apply_energy_cost=True)

    # -------------------------
    # Cursor motion helpers
    # -------------------------

    def _update_cursor_motion_state(self):
        cursor_pos = QCursor.pos()

        if self.ctx.last_cursor_pos is None:
            self.ctx.last_cursor_pos = cursor_pos
            self.ctx.cursor_still_ticks = 0
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

    def _cursor_is_reachable_in_y(self, cursor_pos: QPoint) -> bool:
        min_y = self.pet.y() + int(self.pet.height() * 0.35)
        max_y = self.pet.y() + self.pet.height()
        return min_y <= cursor_pos.y() <= max_y

    def _face_cursor(self, cursor_pos: QPoint):
        desired_facing_right = cursor_pos.x() >= self.pet.x() + self.pet.width() // 2
        if self.pet.animation_player.facing_right != desired_facing_right:
            self.pet.set_facing_right(desired_facing_right)

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

    def _should_continue_swat(self, cursor_pos: QPoint) -> bool:
        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            front_x = self.pet.x() + self.pet.width() - self.ctx.cursor_front_gap
        else:
            front_x = self.pet.x() + self.ctx.cursor_front_gap

        min_y = self.pet.y() + int(self.pet.height() * 0.40) - self.ctx.swat_release_margin_y
        max_y = self.pet.y() + self.pet.height() + self.ctx.swat_release_margin_y

        return (
            abs(cursor_pos.x() - front_x)
            <= (self.ctx.swat_reach_x + self.ctx.swat_release_margin_x)
            and min_y <= cursor_pos.y() <= max_y
        )

    def _should_hold_swat_without_moving(self, cursor_pos: QPoint) -> bool:
        pet_left = self.pet.x() - self.ctx.swat_reach_x
        pet_right = self.pet.x() + self.pet.width() + self.ctx.swat_reach_x

        return (
            pet_left <= cursor_pos.x() <= pet_right
            and self._cursor_is_reachable_in_y(cursor_pos)
        )

    def _should_hold_chase_without_moving(self, cursor_pos: QPoint) -> bool:
        pet_left = self.pet.x() - self.ctx.swat_reach_x
        pet_right = self.pet.x() + self.pet.width() + self.ctx.swat_reach_x

        return (
            pet_left <= cursor_pos.x() <= pet_right
            and self._cursor_is_reachable_in_y(cursor_pos)
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

    # -------------------------
    # Chase / swat state machine
    # -------------------------

    def start_cursor_chase(self):
        self.controller._reset_motion_flags()
        self.ctx.is_chasing_cursor = True
        self.ctx.is_swatting_cursor = False

        self.controller._set_logical_state(PetState.RUN)
        self.pet.play_node(
            AnimationNode.RUNNING,
            replace=True,
            force_restart=True,
        )

        self.chase_timer.start(1800)

    def finish_cursor_chase(self):
        self.cancel()
        self.controller.start_idle()

        self.ctx.cursor_chase_cooldown = True
        self.cursor_chase_cooldown_timer.start(4000)

    def finish_cursor_chase_cooldown(self):
        self.ctx.cursor_chase_cooldown = False

    def _enter_swat_mode(self, apply_energy_cost: bool = True):
        """
        Общий вход в swat-mode:
        - используется и для обычного swat,
        - и для swat после startled.

        Здесь должны жить ВСЕ side effects swat,
        включая удержание курсора.
        """
        self.ctx.is_chasing_cursor = False
        self.ctx.is_swatting_cursor = True
        self.ctx.is_walking = False
        self.chase_timer.stop()

        self.ctx.swat_count_in_encounter += 1

        if apply_energy_cost:
            self.controller.needs.apply_swat_cost()

        self.controller._set_logical_state(PetState.SWAT)

        cursor_pos = QCursor.pos()
        self.pet.set_facing_right(cursor_pos.x() >= self.pet.x() + self.pet.width() // 2)

        self.pet.play_node(
            AnimationNode.SWATTING,
            replace=True,
            force_restart=True,
        )

        self.swat_timer.stop()
        self.swat_timer.start(self.ctx.swat_timeout_ms)

        # Если у тебя уже добавлена "вязкость"/сопротивление курсора,
        # запускаем её здесь — в ОБЩЕМ месте входа в swat.
        if hasattr(self, "cursor_resist_timer"):
            self._cursor_resist_velocity_x = 0.0
            self._cursor_resist_velocity_y = 0.0

            if getattr(self.ctx, "swat_cursor_resist_enabled", False):
                self.cursor_resist_timer.start(self.ctx.swat_cursor_resist_interval_ms)

    def start_cursor_swat(self):
        self._enter_swat_mode(apply_energy_cost=True)

    def finish_cursor_swat(self, resume_chase=False):
        self.ctx.is_swatting_cursor = False
        self.swat_timer.stop()
        self._rear_startle_pending_swat = False

        if resume_chase:
            self.start_cursor_chase()
        else:
            self.finish_cursor_chase()

    def finish_cursor_swat_due_to_timeout(self):
        if self.ctx.is_swatting_cursor:
            self._start_post_swat_caution()
            self.finish_cursor_swat(resume_chase=False)

    def apply_swat_cursor_resistance(self):
        """
        Более "игровое" сопротивление курсору:
        - dead zone около лапы;
        - пружина тянет обратно;
        - velocity накапливается и затухает (damping);
        - сила ограничивается, чтобы не было резких телепортов;
        - если пользователь дёрнул слишком сильно, курсор временно почти отпускаем.
        """
        if not self.ctx.is_swatting_cursor:
            return

        cursor_pos = QCursor.pos()
        anchor_x, anchor_y = self._get_swat_resist_anchor()

        dx = float(cursor_pos.x()) - anchor_x
        dy = float(cursor_pos.y()) - anchor_y

        distance_sq = dx * dx + dy * dy
        dead_zone = float(self.ctx.swat_cursor_dead_zone_radius)
        break_distance = float(self.ctx.swat_cursor_break_distance)

        # Если пользователь слишком сильно рванул курсор —
        # не боремся изо всех сил, чтобы ощущение было естественнее.
        if distance_sq >= break_distance * break_distance:
            self._cursor_resist_velocity_x *= 0.5
            self._cursor_resist_velocity_y *= 0.5
            return

        # Внутри dead zone ничего не делаем
        if distance_sq <= dead_zone * dead_zone:
            self._cursor_resist_velocity_x *= 0.5
            self._cursor_resist_velocity_y *= 0.5
            return

        # Пружинная сила: тянет к anchor
        spring_strength = self.ctx.swat_cursor_spring_strength
        damping = self.ctx.swat_cursor_damping
        max_pull = self.ctx.swat_cursor_max_pull_per_tick

        force_x = -dx * spring_strength
        force_y = -dy * spring_strength

        # Накопление + демпфирование
        self._cursor_resist_velocity_x = (self._cursor_resist_velocity_x + force_x) * damping
        self._cursor_resist_velocity_y = (self._cursor_resist_velocity_y + force_y) * damping

        # Ограничиваем максимум сдвига за тик
        move_x = max(-max_pull, min(max_pull, self._cursor_resist_velocity_x))
        move_y = max(-max_pull, min(max_pull, self._cursor_resist_velocity_y))

        if abs(move_x) < 0.5 and abs(move_y) < 0.5:
            return

        new_x = int(cursor_pos.x() + move_x)
        new_y = int(cursor_pos.y() + move_y)

        if new_x != cursor_pos.x() or new_y != cursor_pos.y():
            QCursor.setPos(new_x, new_y)

    def _get_swat_resist_anchor(self) -> tuple[float, float]:
        """
        Точка, к которой "пружина" пытается слегка вернуть курсор.
        Берём переднюю часть манула около лапы.
        """
        facing_right = self.pet.animation_player.facing_right

        if facing_right:
            anchor_x = self.pet.x() + self.pet.width() - self.ctx.cursor_front_gap
        else:
            anchor_x = self.pet.x() + self.ctx.cursor_front_gap

        anchor_y = self.pet.y() + int(self.pet.height() * 0.70)
        return float(anchor_x), float(anchor_y)

    # -------------------------
    # Periodic AI tick
    # -------------------------

    def check_cursor_proximity(self):
        if self.ctx.is_eating:
            return

        cursor_pos = self._update_cursor_motion_state()

        rear_zone_now = (
            self._cursor_is_near_pet(cursor_pos)
            and self._cursor_is_behind_pet(cursor_pos)
        )
        rear_zone_entered = rear_zone_now and not self._rear_zone_prev
        self._rear_zone_prev = rear_zone_now

        # Сбрасываем latch, когда курсор ушёл от манула
        if not self._cursor_is_near_pet(cursor_pos):
            self._rear_startle_latched = False

        # Если startled -> swatting sequence уже в процессе,
        # ждём, когда реально дошли до SWATTING
        if self._rear_startle_pending_swat:
            if self.pet.current_animation_node() == AnimationNode.SWATTING:
                self._activate_swat_after_startled()
            return

        # IMPORTANT:
        # startled срабатывает ТОЛЬКО если манул в sitting_idle
        # и курсор именно ВОШЁЛ в заднюю зону.
        if (
            self.pet.current_animation_node() == AnimationNode.SITTING_IDLE
            and not self.ctx.is_chasing_cursor
            and not self.ctx.is_swatting_cursor
            and not self.ctx.is_falling
            and not self.ctx.is_walking
            and not self.ctx.is_dragging
            and not self.ctx.is_recovering
            and not self.ctx.is_cleaning
            and not self.ctx.is_sleeping
            and not self.ctx.is_eating
            and not self.ctx.is_investigating_notifications
            and not self.ctx.cursor_chase_cooldown
        ):
            if rear_zone_entered and not self._rear_startle_latched:
                self.start_rear_startled_swat(cursor_pos)
                return

        # FEED cursor + голод -> немедленно просим еду вместо swat
        if self._feed_mode_active() and self._is_hungry_for_feed():
            if self._cursor_is_near_pet(cursor_pos) and self._cursor_is_reachable_in_y(cursor_pos):
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

            if self._should_continue_swat(cursor_pos) and self._cursor_is_stationary_enough():
                if self.pet.current_animation_node() != AnimationNode.SWATTING:
                    self.pet.play_node(
                        AnimationNode.SWATTING,
                        replace=True,
                        force_restart=True,
                    )
                return

            if self._cursor_is_near_pet(cursor_pos) and self._cursor_is_reachable_in_y(cursor_pos):
                self.finish_cursor_swat(resume_chase=True)
            else:
                self._reset_swat_encounter()
                self.finish_cursor_swat(resume_chase=False)
            return

        # Уже chasing
        if self.ctx.is_chasing_cursor:
            if not self._cursor_is_reachable_in_y(cursor_pos):
                self._reset_swat_encounter()
                self.finish_cursor_chase()
                return

            if self._should_hold_chase_without_moving(cursor_pos):
                self._face_cursor(cursor_pos)

                # В контактной зоне не держим frozen RUNNING,
                # а переводим в standing-like neutral pose
                if self.pet.current_animation_node() != AnimationNode.STANDING_IDLE:
                    self.pet.play_node(
                        AnimationNode.STANDING_IDLE,
                        replace=True,
                        force_restart=True,
                    )

                if self._can_swat_cursor(cursor_pos) and self._cursor_is_stationary_enough():
                    if self.ctx.swat_count_in_encounter < self.ctx.max_swats_per_encounter:
                        self.start_cursor_swat()
                    else:
                        self.finish_cursor_chase()
                return

            if self._can_swat_cursor(cursor_pos) and self._cursor_is_stationary_enough():
                if self.ctx.swat_count_in_encounter < self.ctx.max_swats_per_encounter:
                    self.start_cursor_swat()
                else:
                    self.finish_cursor_chase()
                return

        # Встреча закончилась
        if not self._cursor_is_near_pet(cursor_pos):
            self._reset_swat_encounter()

        # Если заняты другими сценариями — не стартуем chase
        if (
            self.ctx.is_falling
            or self.ctx.is_walking
            or self.ctx.is_dragging
            or self.ctx.is_recovering
            or self.ctx.is_cleaning
            or self.ctx.is_sleeping
            or self.ctx.is_meowing
            or self.ctx.is_eating
            or self.ctx.is_investigating_notifications
            or self.ctx.cursor_chase_cooldown
            or self.ctx.is_pooping
            or self.ctx.is_post_pooping_zoomies
            or self.ctx.is_hiding
        ):
            return

        if self._cursor_is_near_pet(cursor_pos) and self._cursor_is_reachable_in_y(cursor_pos):
            trigger_chance = self._current_chase_trigger_chance()
            if random.random() < trigger_chance:
                self.start_cursor_chase()

    # -------------------------
    # Movement hook
    # -------------------------

    def process_chase_step(self) -> bool:
        if self.ctx.is_hiding:
            return False
        if self.ctx.is_pooping or self.ctx.is_post_pooping_zoomies:
            return False
        if self.ctx.is_eating:
            return False

        if self.ctx.is_swatting_cursor:
            return True

        if self.ctx.is_chasing_cursor and not self.ctx.is_dragging:
            cursor_pos = QCursor.pos()

            if not self._cursor_is_reachable_in_y(cursor_pos):
                self._reset_swat_encounter()
                self.finish_cursor_chase()
                return True

            if self._should_hold_chase_without_moving(cursor_pos):
                self._face_cursor(cursor_pos)

                if self.pet.current_animation_node() != AnimationNode.STANDING_IDLE:
                    self.pet.play_node(
                        AnimationNode.STANDING_IDLE,
                        replace=True,
                        force_restart=True,
                    )
                return True

            current_x = self.pet.x()
            target_x, direction = self._get_cursor_chase_target_x(cursor_pos)

            self.pet.set_facing_right(direction == 1)

            if self.pet.current_animation_node() != AnimationNode.RUNNING:
                self.pet.play_node(
                    AnimationNode.RUNNING,
                    replace=True,
                    force_restart=True,
                )

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