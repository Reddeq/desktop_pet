import random

from PyQt6.QtCore import QObject, QTimer, QPoint

from animation_node import AnimationNode
from pet_behavior import PetBehavior
from pet_context import PetContext
from pet_cursor_ai import PetCursorAI
from pet_motion import PetMotion
from pet_needs import PetNeeds
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

        self.scratching_timer = QTimer(self)
        self.scratching_timer.setSingleShot(True)
        self.scratching_timer.timeout.connect(self.finish_scratching_for_food)

        self.needs_timer = QTimer(self)
        self.needs_timer.timeout.connect(self._on_needs_tick)

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

        self.needs = PetNeeds(parent=self)

        # -------------------------
        # Notification / digging runtime state
        # -------------------------
        self.notification_target_x: int | None = None
        self.notification_motion_started = False
        self.notification_dig_started = False

    # -------------------------
    # Lifecycle
    # -------------------------

    def start(self):
        self.logic_timer.start(5000)
        self.gravity_timer.start(20)
        self.walk_timer.start(16)
        self.needs_timer.start(1000)
        self.cursor_ai.start()

    def stop(self):
        self.logic_timer.stop()
        self.gravity_timer.stop()
        self.walk_timer.stop()
        self.cleaning_timer.stop()
        self.dig_timer.stop()
        self.needs_timer.stop()
        self.cursor_ai.stop()
        self.scratching_timer.stop()

    # -------------------------
    # High-level logical state
    # -------------------------

    def _set_logical_state(self, state: PetState):
        """
        High-level logical state for needs / debug / behavior.
        Больше НЕ используется как API анимаций.
        """
        self.pet.current_state = state

    # -------------------------
    # Periodic ticks
    # -------------------------

    def _on_logic_tick(self):
        self.behavior.tick()

    def _on_needs_tick(self):
        self.needs.tick(
            logical_state=self.pet.current_state,
            current_animation_node=self.pet.current_animation_node(),
        )

        if self.ctx.is_sleeping and self.needs.values.energy >= 100.0:
            self.finish_sleep()

    # -------------------------
    # Animation finished hook
    # -------------------------

    def on_animation_finished(self, animation_name: str):
        """
        Controller не управляет обычными переходами анимаций вручную —
        это делает PetAnimator.

        Здесь остаются только side-effects сценариев/логики.
        """
        try:
            finished_node = AnimationNode(animation_name)
        except ValueError:
            return

        # После завершения falling_recovery one-shot
        # логически завершаем recovery state
        if finished_node == AnimationNode.FALLING_RECOVERY and self.ctx.is_recovering:
            self.motion.finish_fall_recovery()

    # -------------------------
    # Internal state cleanup
    # -------------------------

    def _stop_cleaning(self):
        self.ctx.is_cleaning = False
        self.cleaning_timer.stop()

    def _stop_notification_investigation(self):
        self.ctx.is_investigating_notifications = False
        self.dig_timer.stop()

        self.notification_target_x = None
        self.notification_motion_started = False
        self.notification_dig_started = False

    def _stop_scratching_for_food(self):
        self.ctx.is_scratching_for_food = False
        self.scratching_timer.stop()

    def _stop_sleeping(self):
        self.ctx.is_sleeping = False

    def _reset_motion_flags(self):
        self.ctx.is_falling = False
        self.ctx.gravity_speed = 0
        self.ctx.is_walking = False
        self.ctx.is_recovering = False

        self._stop_cleaning()
        self._stop_notification_investigation()
        self._stop_scratching_for_food()
        self._stop_sleeping()

        self.cursor_ai.cancel()
        

    # -------------------------
    # External needs actions
    # -------------------------

    def feed(self):
        self.needs.feed()

    def use_toilet(self):
        self.needs.use_toilet()

    def try_feed(self) -> bool:
        """
        Если манул голоден (< 50), кормим:
        - immediately EATING
        - satiety = 100
        - bladder -= 50
        """
        if self.ctx.is_sleeping:
            return False

        if self.needs.values.satiety >= self.ctx.food_begging_satiety_threshold:
            return False

        self._reset_motion_flags()
        self.needs.feed_full_meal(
            bladder_penalty=self.ctx.feed_full_meal_bladder_penalty
        )

        self._set_logical_state(PetState.IDLE)

        self.pet.play_sequence_nodes(
            [
                AnimationNode.EATING,
                AnimationNode.SITTING_IDLE,
            ],
            replace=True,
            force_restart=True,
        )
        return True

    # -------------------------
    # Idle
    # -------------------------

    def start_idle(self):
        self._set_logical_state(PetState.IDLE)
        self.pet.play_node(
            AnimationNode.SITTING_IDLE,
            replace=True,
            force_restart=True,
        )

    # -------------------------
    # Sleep
    # -------------------------

    def start_sleep(self):
        self._reset_motion_flags()
        self.ctx.is_sleeping = True
        self._set_logical_state(PetState.SLEEP)

        # Граф сам подставит переходы до SLEEPING
        self.pet.play_node(
            AnimationNode.SLEEPING,
            replace=True,
            force_restart=True,
        )

    def finish_sleep(self):
        self.ctx.is_sleeping = False
        self.start_idle()

    # -------------------------
    # Cleaning
    # -------------------------

    def start_cleaning(self):
        self._reset_motion_flags()
        self.ctx.is_cleaning = True
        self._set_logical_state(PetState.CLEANING)

        self.pet.play_node(
            AnimationNode.CLEANING,
            replace=True,
            force_restart=True,
        )

        duration_ms = random.randint(2000, 5000)
        self.cleaning_timer.start(duration_ms)

    def finish_cleaning(self):
        self.ctx.is_cleaning = False
        self.start_idle()

    # -------------------------
    # Notification / digging scenario
    # -------------------------

    def start_notification_investigation(self):
        """
        Sequence-driven сценарий:
            ALERT -> RUNNING -> DIGGING

        Промежуточные переходы добавляет PetAnimator по animation graph.
        """
        self._reset_motion_flags()
        self.ctx.is_investigating_notifications = True
        self._set_logical_state(PetState.ALERT)

        self.notification_target_x = self.motion.get_tray_target_x()
        self.notification_motion_started = False
        self.notification_dig_started = False

        self.pet.play_sequence_nodes(
            [
                AnimationNode.ALERT,
                AnimationNode.RUNNING,
                AnimationNode.DIGGING,
            ],
            replace=True,
            force_restart=True,
        )

    def _sync_notification_sequence(self):
        if not self.ctx.is_investigating_notifications:
            return

        current_node = self.pet.current_animation_node()

        # Когда sequence реально дошла до RUNNING — запускаем физическое движение
        if (
            current_node == AnimationNode.RUNNING
            and not self.notification_motion_started
            and self.notification_target_x is not None
        ):
            self.notification_motion_started = True
            self._set_logical_state(PetState.RUN)
            self.motion.start_run_to_x(self.notification_target_x)
            return

        # Когда sequence реально дошла до DIGGING — запускаем digging phase
        if (
            current_node == AnimationNode.DIGGING
            and not self.notification_dig_started
        ):
            self.notification_dig_started = True
            self._set_logical_state(PetState.DIG)

            duration_ms = random.randint(2000, 4000)
            self.dig_timer.start(duration_ms)
            return

    def finish_notification_investigation(self):
        self._stop_notification_investigation()
        self.start_idle()

    def start_scratching_for_food(self):
        self._reset_motion_flags()
        self.ctx.is_scratching_for_food = True
        self._set_logical_state(PetState.IDLE)

        self.pet.play_node(
            AnimationNode.SCRATCHING_SCREEN,
            replace=True,
            force_restart=True,
        )

        duration_ms = random.randint(1800, 3500)
        self.scratching_timer.start(duration_ms)

    def finish_scratching_for_food(self):
        self.ctx.is_scratching_for_food = False
        self.start_idle()

    # -------------------------
    # Movement processing
    # -------------------------

    def process_walk_step(self):
        # Cursor AI может полностью перехватить движение
        if self.cursor_ai.process_chase_step():
            return

        # Синхронизация notification-sequence с motion/dig
        self._sync_notification_sequence()

        # Физическое движение
        self.motion.process_walk_step()

    # -------------------------
    # Gravity / falling recovery
    # -------------------------

    def apply_gravity(self):
        self.motion.apply_gravity()

    # -------------------------
    # Mouse drag / falling interrupt
    # -------------------------

    def on_mouse_press(self, global_pos):
        self._reset_motion_flags()
        self.ctx.is_dragging = True
        self.ctx.old_pos = global_pos.toPoint()

        self._set_logical_state(PetState.FALLING)

        # Falling — только interrupt
        self.pet.interrupt_animation(
            AnimationNode.FALLING,
            recovery_targets=[
                AnimationNode.FALLING_RECOVERY,
                AnimationNode.STANDING_IDLE,
            ],
        )

    def on_mouse_move(self, global_pos):
        if self.ctx.old_pos is None:
            self.ctx.old_pos = global_pos.toPoint()
            return

        delta = QPoint(global_pos.toPoint() - self.ctx.old_pos)

        new_x = self.pet.x() + delta.x()
        new_y = self.pet.y() + delta.y()

        new_x, new_y = self.pet.clamp_position(new_x, new_y)

        self.pet.move(new_x, new_y)
        self.ctx.old_pos = global_pos.toPoint()

    def on_mouse_release(self):
        self.ctx.is_dragging = False
        self.ctx.old_pos = None

        if self.pet.y() < self.pet.ground_y:
            self.ctx.is_falling = True
            self.ctx.gravity_speed = 0
            self._set_logical_state(PetState.FALLING)
        else:
            # Если отпустили сразу на земле — завершаем interrupt без физического падения
            self.ctx.is_recovering = True
            self.pet.resolve_animation_interrupt()