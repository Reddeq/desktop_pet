from PyQt6.QtCore import QObject

from animation_node import AnimationNode
from pet_state import PetState
import random


class PetMotion(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx
        self._screen_motion_rect = None
        self._screen_exit = False
        self._screen_keep_clip = False

        self.motion_animation_nodes = {
            AnimationNode.WALK,
            AnimationNode.RUN,
            AnimationNode.SNEAK,
        }

    # -------------------------
    # Generic horizontal movement
    # -------------------------

    def start_walk(self, direction: int, distance: int) -> bool:
        """
        Запускает обычное перемещение на фиксированную дистанцию.

        Возвращает True, если движение реально стартовало.
        Возвращает False, если идти некуда (например, у края экрана).
        """
        self.ctx.walk_direction = direction
        self.pet.set_facing_right(direction == 1)

        target_x = self.pet.x() + (direction * distance)
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == self.pet.x():
            self.ctx.is_walk = False
            self.ctx.walk_target_x = self.pet.x()
            return False

        self.ctx.walk_target_x = target_x
        self.ctx.is_walk = True
        return True

    def start_run_to_x(self, target_x: int, *, allow_partial=False) -> bool:
        """
        Запускает движение к конкретной X-координате.

        Возвращает True, если движение реально стартовало.
        Возвращает False, если уже стоим в целевой точке.
        """
        current_x = self.pet.x()
        if allow_partial:
            screen = self.pet.get_current_screen_rect()
            target_x = max(screen.left() - self.pet.width() + 1, min(target_x, screen.right()))
            self._screen_motion_rect = screen
            self._screen_keep_clip = True
            self._screen_exit = False
            self.pet.set_screen_clip(screen)
        else:
            target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == current_x:
            self.ctx.is_walk = False
            self.ctx.walk_target_x = current_x
            return False

        direction = 1 if target_x > current_x else -1
        self.ctx.walk_direction = direction
        self.ctx.walk_target_x = target_x
        self.ctx.is_walk = True

        self.pet.set_facing_right(direction == 1)
        return True

    def stop_horizontal_motion(self):
        """
        Немедленно останавливает текущий walk/run сегмент.
        """
        self.ctx.is_walk = False
        self.ctx.walk_target_x = self.pet.x()
        self._screen_exit = False
        self._screen_keep_clip = False
        if self._screen_motion_rect is not None:
            self._screen_motion_rect = None
            self.pet.set_screen_clip(None)
            x, y = self.pet.clamp_position(self.pet.x(), self.pet.ground_y)
            self.pet.move(x, y)

    def start_screen_entry(self, edge=None):
        """Reveal RUN progressively from outside the bound screen."""
        edge = edge or random.choice(('left', 'right'))
        self.pet.set_horizontal_edge_anchor(None)
        self.controller._set_logical_state(PetState.RUN)
        self.pet.set_facing_right(edge == 'left')
        self.pet.force_set_animation_node(AnimationNode.RUN)
        if self.pet.current_animation_node() != AnimationNode.RUN:
            return False
        screen = self.pet.get_current_screen_rect()
        self._screen_motion_rect = screen
        self._screen_exit = False
        self._screen_keep_clip = False
        margin = min(80, max(0, (screen.width() - self.pet.width()) // 2))
        if edge == 'left':
            start_x, target_x = screen.left() - self.pet.width(), screen.left() + margin
        else:
            start_x = screen.right() + 1
            target_x = screen.right() + 1 - self.pet.width() - margin
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)
        self.ctx.walk_direction = 1 if edge == 'left' else -1
        self.ctx.walk_target_x = target_x
        self.ctx.is_walk = True
        self.pet.set_screen_clip(screen)
        self.pet.move(start_x, self.pet.ground_y)
        self.pet.show()
        return True

    def start_screen_exit(self, edge):
        """Keep running until the entire window has crossed the screen edge."""
        screen = self.pet.get_current_screen_rect()
        self.pet.set_horizontal_edge_anchor(None)
        self._screen_motion_rect = screen
        self._screen_exit = True
        self._screen_keep_clip = False
        self.ctx.walk_direction = -1 if edge == 'left' else 1
        self.ctx.walk_target_x = (screen.left() - self.pet.width() if edge == 'left'
                                  else screen.right() + 1)
        self.ctx.is_walk = True
        self.pet.set_facing_right(edge == 'right')
        self.pet.set_screen_clip(screen)

    def get_tray_target_x(self):
        screen_rect = self.pet.get_current_screen_rect()
        margin = 40
        return screen_rect.x() + screen_rect.width() - self.pet.width() - margin

    def process_walk_step(self):
        if not self.ctx.is_walk or self.ctx.is_drag:
            return

        current_node = self.pet.current_animation_node()

        if current_node not in self.motion_animation_nodes:
            return

        current_x = self.pet.x()

        if self.ctx.walk_direction == 1:
            raw_next_x = min(current_x + self.ctx.walk_speed, self.ctx.walk_target_x)
        else:
            raw_next_x = max(current_x - self.ctx.walk_speed, self.ctx.walk_target_x)

        if self._screen_motion_rect is not None:
            new_x, new_y = raw_next_x, self.pet.ground_y
        else:
            new_x, new_y = self.pet.clamp_position(raw_next_x, self.pet.ground_y)

        self.pet.move(new_x, new_y)

        # 1) Обычное успешное достижение цели
        if new_x == self.ctx.walk_target_x:
            self.ctx.is_walk = False
            if self._screen_motion_rect is not None and not self._screen_keep_clip:
                if self._screen_exit:
                    # Hide before releasing the mask, including on two monitors.
                    self.pet.hide()
                self._screen_motion_rect = None
                self._screen_exit = False
                self.pet.set_screen_clip(None)
            self.pet.animator.notify_motion_complete()
            return

        # 2) Защита: если clamp не даёт сдвинуться дальше,
        #    считаем движение завершённым/заблокированным
        if new_x == current_x:
            self.ctx.is_walk = False
            self.ctx.walk_target_x = new_x
            self.pet.animator.notify_motion_complete()
    
    # -------------------------
    # Gravity / landing / interrupt recovery
    # -------------------------

    def _land(self):
        self.controller.surfaces.land_from_fall()
        self.ctx.is_fall = False
        self.ctx.gravity_speed = 0
        self.pet.move(self.pet.x(), self.pet.ground_y)
        self.start_fall_recovery()

    def apply_gravity(self):
        if not self.ctx.is_fall:
            return

        if self.pet.y() < self.pet.ground_y:
            self.ctx.gravity_speed += 2
            new_y = self.pet.y() + self.ctx.gravity_speed

            if new_y >= self.pet.ground_y:
                self._land()
                return

            self.pet.move(self.pet.x(), new_y)
        else:
            self._land()

    def start_fall_recovery(self):
        self.ctx.is_recover = True
        self.controller._set_logical_state(PetState.RECOVER)

        if self.pet.animator.is_interrupt_active:
            self.pet.animator.resolve_interrupt()
        else:
            # A missing fall clip may already have cleared the interrupt.
            self.pet.animator.force_set_node(AnimationNode.RECOVER)
            if self.pet.current_animation_node() == AnimationNode.RECOVER:
                self.pet.play_sequence_nodes([AnimationNode.STAND_IDLE], replace=False)

    def finish_fall_recovery(self):
        self.ctx.is_recover = False
        self.controller._set_logical_state(PetState.IDLE)
