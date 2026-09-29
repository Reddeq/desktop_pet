"""Coordinates physics, cursor interaction, needs and behavior lifecycle."""
from PyQt6.QtCore import QObject, QTimer, QPoint

from animation_node import AnimationNode
from behavior_runtime import BehaviorManager
from pet_behavior import PetBehavior
from pet_context import PetContext
from pet_cursor_ai import PetCursorAI
from pet_motion import PetMotion
from pet_needs import PetNeeds
from pet_state import PetState


class PetController(QObject):
    def __init__(self, pet, parent=None, plugin_dirs=None):
        super().__init__(parent)
        self.pet = pet
        self.ctx = PetContext()
        self.needs = PetNeeds(parent=self)
        self.motion = PetMotion(self, pet, self.ctx, parent=self)
        self.cursor_ai = PetCursorAI(self, pet, self.ctx, parent=self)
        self.behaviors = BehaviorManager(self, plugin_dirs=plugin_dirs)
        self.pet.animator.animation_failed.connect(self._on_animation_failed)
        self.behavior = PetBehavior(self, parent=self)
        self.logic_timer = self._timer(self.behavior.tick, 5000)
        self.gravity_timer = self._timer(self.motion.apply_gravity, 20)
        self.walk_timer = self._timer(self.process_walk_step, 16)
        self.needs_timer = self._timer(self._on_needs_tick, 1000)

    def _timer(self, callback, interval):
        timer = QTimer(self)
        timer.setInterval(interval)
        timer.timeout.connect(callback)
        return timer

    def start(self):
        for timer in (self.logic_timer, self.gravity_timer, self.walk_timer, self.needs_timer):
            timer.start()
        self.cursor_ai.start()

    def stop(self):
        for timer in (self.logic_timer, self.gravity_timer, self.walk_timer, self.needs_timer):
            timer.stop()
        self.behaviors.cancel()
        self.cursor_ai.cancel()
        self.cursor_ai.stop()

    @property
    def interaction_locked(self):
        return (self.ctx.is_dragging or self.ctx.is_falling
                or self.ctx.is_recovering or self.ctx.is_menu_open)

    def is_busy(self):
        return (self.interaction_locked or self.behaviors.active is not None
                or self.ctx.is_walking or self.cursor_ai.is_busy())

    def _set_logical_state(self, state):
        self.pet.current_state = state

    def _on_needs_tick(self):
        self.needs.tick(self.pet.current_state, self.pet.current_animation_node())
        self.behaviors.needs_tick()

    def _on_animation_failed(self, name):
        active = self.behaviors.active
        if active is not None:
            self.behaviors.errors.append(f"{active.id}: missing animation {name}")
            self.behaviors.disabled.add(active.id)
        self.behaviors.cancel()
        self.cursor_ai.cancel()
        if name != AnimationNode.SITTING_IDLE.value:
            self.start_idle()

    def on_animation_finished(self, animation_name):
        try:
            node = AnimationNode(animation_name)
        except ValueError:
            return
        if node == AnimationNode.FALLING_RECOVERY and self.ctx.is_recovering:
            self.motion.finish_fall_recovery()
        self.behaviors.dispatch("on_animation_finished", node)

    def _reset_motion_flags(self):
        self.behaviors.cancel()
        self.cursor_ai.cancel()
        self.ctx.is_falling = False
        self.ctx.gravity_speed = 0
        self.ctx.is_recovering = False
        self.pet.animator.clear()

    def start_behavior(self, behavior_id):
        if self.interaction_locked:
            return False
        return self.behaviors.start(behavior_id)

    def start_idle(self):
        self.behaviors.cancel()
        self._set_logical_state(PetState.IDLE)
        self.pet.play_node(AnimationNode.SITTING_IDLE, replace=True, force_restart=True)

    def process_walk_step(self):
        if not self.cursor_ai.process_chase_step():
            self.motion.process_walk_step()
        self.behaviors.dispatch("on_tick")

    def start_falling(self):
        self._reset_motion_flags()
        self.ctx.is_falling = True
        self._set_logical_state(PetState.FALLING)
        self.pet.interrupt_animation(
            AnimationNode.FALLING,
            recovery_targets=[AnimationNode.FALLING_RECOVERY, AnimationNode.STANDING_IDLE],
        )

    def on_mouse_press(self, global_pos):
        self.start_falling()
        self.ctx.is_falling = False
        self.ctx.is_dragging = True
        self.ctx.old_pos = global_pos.toPoint()

    def on_mouse_move(self, global_pos):
        if not self.ctx.is_dragging:
            return
        if self.ctx.old_pos is None:
            self.ctx.old_pos = global_pos.toPoint()
            return
        delta = QPoint(global_pos.toPoint() - self.ctx.old_pos)
        x, y = self.pet.clamp_position_for_drag(
            self.pet.x() + delta.x(), self.pet.y() + delta.y(), global_pos.toPoint(),
        )
        self.pet.move(x, y)
        self.ctx.old_pos = global_pos.toPoint()

    def on_mouse_release(self):
        if not self.ctx.is_dragging:
            return
        self.ctx.is_dragging = False
        self.ctx.old_pos = None
        if self.pet.y() < self.pet.ground_y:
            self.ctx.is_falling = True
            self.ctx.gravity_speed = 0
            self._set_logical_state(PetState.FALLING)
        else:
            self.motion.start_fall_recovery()

    def try_feed(self):
        if self.interaction_locked or self.ctx.is_sleeping:
            return False
        if self.needs.values.satiety >= self.ctx.food_begging_satiety_threshold:
            return False
        if not self.start_behavior("eating"):
            return False
        self.needs.feed_full_meal(self.ctx.feed_full_meal_bladder_penalty)
        return True

    def feed(self):
        self.needs.feed()

    def use_toilet(self):
        self.needs.use_toilet()

    def set_need_value(self, name, value):
        if not self.needs.debug_set_need(name, value):
            return False
        self.behaviors.dispatch("on_needs")
        return True

    def start_menu_meowing(self):
        if self.ctx.is_menu_open:
            return
        active = self.behaviors.active
        # Preserve hiding and physical interrupts while a popup is open.
        if not self.interaction_locked and not (active and active.preserve_on_menu):
            self.behaviors.start("menu_meowing")
        self.ctx.is_menu_open = True

    def finish_menu_meowing(self):
        self.ctx.is_menu_open = False
        self._finish_behavior("menu_meowing")

    # Compatibility entry points for existing cursor/UI callers. New scripts
    # use start_behavior(id); no new wrapper or enum entry is needed.
    def _finish_behavior(self, behavior_id):
        active = self.behaviors.active
        if active is not None and active.id == behavior_id:
            active.finish()

    def start_scratching_for_food(self):
        return self.start_behavior("food_begging")

    def finish_scratching_for_food(self):
        self._finish_behavior("food_begging")

    def debug_start_hiding(self):
        return self.start_behavior("hiding")
