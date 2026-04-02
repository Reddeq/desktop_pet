from PyQt6.QtCore import QObject

from animation_node import AnimationNode


class PetMotion(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx

        self.motion_animation_nodes = {
            AnimationNode.WALKING,
            AnimationNode.RUNNING,
            AnimationNode.HUNTING,
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
            self.ctx.is_walking = False
            self.ctx.walk_target_x = self.pet.x()
            return False

        self.ctx.walk_target_x = target_x
        self.ctx.is_walking = True
        return True

    def start_run_to_x(self, target_x: int) -> bool:
        """
        Запускает движение к конкретной X-координате.

        Возвращает True, если движение реально стартовало.
        Возвращает False, если уже стоим в целевой точке.
        """
        current_x = self.pet.x()
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == current_x:
            self.ctx.is_walking = False
            self.ctx.walk_target_x = current_x
            return False

        direction = 1 if target_x > current_x else -1
        self.ctx.walk_direction = direction
        self.ctx.walk_target_x = target_x
        self.ctx.is_walking = True

        self.pet.set_facing_right(direction == 1)
        return True

    def stop_horizontal_motion(self):
        """
        Немедленно останавливает текущий walk/run сегмент.
        """
        self.ctx.is_walking = False
        self.ctx.walk_target_x = self.pet.x()

    def get_tray_target_x(self):
        screen_rect = self.pet.get_current_screen_rect()
        margin = 40
        return screen_rect.x() + screen_rect.width() - self.pet.width() - margin

    def process_walk_step(self):
        if not self.ctx.is_walking or self.ctx.is_dragging:
            return

        current_node = self.pet.current_animation_node()

        # Двигаемся только если аниматор реально находится
        # в motion-capable animation node.
        if current_node not in self.motion_animation_nodes:
            return

        current_x = self.pet.x()

        if self.ctx.walk_direction == 1:
            new_x = min(current_x + self.ctx.walk_speed, self.ctx.walk_target_x)
        else:
            new_x = max(current_x - self.ctx.walk_speed, self.ctx.walk_target_x)

        new_x, new_y = self.pet.clamp_position(new_x, self.pet.ground_y)
        self.pet.move(new_x, new_y)

        if new_x == self.ctx.walk_target_x:
            self.ctx.is_walking = False
            self.pet.animator.notify_motion_complete()

    # -------------------------
    # Gravity / landing / interrupt recovery
    # -------------------------

    def _land(self):
        self.ctx.is_falling = False
        self.ctx.gravity_speed = 0
        self.pet.move(self.pet.x(), self.pet.ground_y)
        self.start_fall_recovery()

    def apply_gravity(self):
        if not self.ctx.is_falling:
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
        self.ctx.is_recovering = True

        if hasattr(self.pet, "resolve_animation_interrupt"):
            self.pet.resolve_animation_interrupt()
        else:
            self.pet.animator.resolve_interrupt()

    def finish_fall_recovery(self):
        self.ctx.is_recovering = False