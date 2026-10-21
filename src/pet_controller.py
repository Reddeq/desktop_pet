"""Coordinates physics, cursor interaction and timed behavior lifecycle."""
from PyQt6.QtCore import QObject, QTimer, QPoint

from animation_node import AnimationNode
from behavior_runtime import BehaviorManager
from pet_context import PetContext
from pet_cursor_ai import PetCursorAI
from pet_motion import PetMotion
from pet_state import PetState


class PetController(QObject):
    def __init__(self, pet, parent=None, plugin_dirs=None):
        super().__init__(parent)
        self.pet = pet
        self.ctx = PetContext()
        self.motion = PetMotion(self, pet, self.ctx, parent=self)
        self.cursor_ai = PetCursorAI(self, pet, self.ctx, parent=self)
        self.behaviors = BehaviorManager(self, plugin_dirs=plugin_dirs)
        self.food_cooldown_until = 0.0
        self.pet.animator.animation_failed.connect(self._on_animation_failed)
        self.logic_timer = self._timer(self.behaviors.logic_tick, 5000)
        self.gravity_timer = self._timer(self.motion.apply_gravity, 20)
        self.walk_timer = self._timer(self.process_walk_step, 16)

    def _timer(self, callback, interval):
        timer = QTimer(self)
        timer.setInterval(interval)
        timer.timeout.connect(callback)
        return timer

    def start(self):
        for timer in (self.logic_timer, self.gravity_timer, self.walk_timer):
            timer.start()
        self.cursor_ai.start()

    def stop(self):
        for timer in (self.logic_timer, self.gravity_timer, self.walk_timer):
            timer.stop()
        self.behaviors.cancel()
        self.cursor_ai.cancel()
        self.cursor_ai.stop()
        self.pet.animator.clear()
        if hasattr(self.pet.animation_player, "timer"):
            self.pet.animation_player.timer.stop()

    @property
    def interaction_locked(self):
        return (self.ctx.is_drag or self.ctx.is_fall
                or self.ctx.is_recover or self.ctx.is_menu_open)

    def is_busy(self):
        return (self.interaction_locked or self.behaviors.active is not None
                or self.ctx.is_walk or self.cursor_ai.is_busy())

    def _set_logical_state(self, state):
        self.pet.current_state = state

    def _on_animation_failed(self, name):
        active = self.behaviors.active
        if active is not None:
            self.behaviors.errors.append(f"{active.id}: missing animation {name}")
            self.behaviors.disabled.add(active.id)
        self.behaviors.cancel()
        self.cursor_ai.cancel()
        self.ctx.is_recover = False
        if name != AnimationNode.SIT_IDLE.value:
            self.start_idle()

    def on_animation_finished(self, animation_name):
        try:
            node = AnimationNode(animation_name)
        except ValueError:
            return
        if node == AnimationNode.RECOVER and self.ctx.is_recover:
            self.motion.finish_fall_recovery()
        self.cursor_ai.on_animation_finished(node)
        self.behaviors.dispatch("on_animation_finished", node)

    def on_animation_loop_finished(self, animation_name):
        try:
            node = AnimationNode(animation_name)
        except ValueError:
            return
        self.cursor_ai.on_animation_loop_finished(node)
        self.behaviors.dispatch("on_animation_loop_finished", node)

    def _reset_motion_flags(self):
        self.behaviors.cancel()
        self.cursor_ai.cancel()
        self.ctx.is_fall = False
        self.ctx.gravity_speed = 0
        self.ctx.is_recover = False
        self.pet.animator.clear()

    def start_behavior(self, behavior_id):
        if self.interaction_locked:
            return False
        return self.behaviors.start(behavior_id)

    def start_idle(self):
        self.behaviors.cancel()
        self._set_logical_state(PetState.IDLE)
        self.pet.play_node(AnimationNode.SIT_IDLE, replace=True, force_restart=True)

    def process_walk_step(self):
        if not self.cursor_ai.process_chase_step():
            self.motion.process_walk_step()
        self.behaviors.dispatch("on_tick")

    def start_fall(self):
        self._reset_motion_flags()
        self.ctx.is_fall = True
        self._set_logical_state(PetState.FALL)
        self.pet.interrupt_animation(
            AnimationNode.FALL,
            recovery_targets=[AnimationNode.RECOVER, AnimationNode.STAND_IDLE],
        )

    def on_mouse_press(self, global_pos):
        self.cursor_ai.jump.cancel(preserve_position=True)
        self._reset_motion_flags()
        self.ctx.is_drag = True
        self._set_logical_state(PetState.DRAG)
        self.pet.interrupt_animation(
            AnimationNode.DRAG,
            recovery_targets=[AnimationNode.RECOVER, AnimationNode.STAND_IDLE],
        )
        self.ctx.old_pos = global_pos.toPoint()

    def on_mouse_move(self, global_pos):
        if not self.ctx.is_drag:
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
        if not self.ctx.is_drag:
            return
        self.ctx.is_drag = False
        self.ctx.old_pos = None
        if self.pet.y() < self.pet.ground_y:
            self.start_fall()
        else:
            self.motion.start_fall_recovery()

    def can_feed(self):
        return not (self.interaction_locked or self.ctx.is_sleep
                or self.ctx.is_eat or self.ctx.is_hide or self.cursor_ai.jump.active
                or self.behaviors._clock() < self.food_cooldown_until)

    def try_feed(self):
        if not self.can_feed():
            return False
        if not self.start_behavior("eat"):
            return False
        self.behaviors.postpone("beg_food")
        return True

    def start_menu_meow(self):
        if self.ctx.is_menu_open:
            return
        active = self.behaviors.active
        # Preserve hide and physical interrupts while a popup is open.
        if not self.interaction_locked and not (active and active.preserve_on_menu):
            self.behaviors.start("menu_meow")
        self.ctx.is_menu_open = True

    def finish_menu_meow(self):
        self.ctx.is_menu_open = False
        self._finish_behavior("menu_meow")

    # Compatibility entry points for existing cursor/UI callers. New scripts
    # use start_behavior(id); no new wrapper or enum entry is needed.
    def _finish_behavior(self, behavior_id):
        active = self.behaviors.active
        if active is not None and active.id == behavior_id:
            active.finish()

    def start_scratch_for_food(self):
        return self.start_behavior("beg_food")

    def finish_scratch_for_food(self):
        self._finish_behavior("beg_food")

    def debug_start_hide(self):
        return self.start_behavior("hide")
