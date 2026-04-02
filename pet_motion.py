from PyQt6.QtCore import QObject


class PetMotion(QObject):
    def __init__(self, controller, pet, ctx, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx

    # -------------------------
    # Generic horizontal movement
    # -------------------------

    def start_walk(self, direction: int, distance: int):
        """
        Запускает обычное перемещение на фиксированную дистанцию.

        ВАЖНО:
        Этот метод больше не включает анимацию сам.
        Какой animation-node сейчас активен (например WALKING) —
        решает PetAnimator / controller / behavior layer.
        """
        self.ctx.walk_direction = direction
        self.pet.set_facing_right(direction == 1)

        target_x = self.pet.x() + (direction * distance)
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == self.pet.x():
            # Двигаться некуда — сразу сообщаем аниматору,
            # что motion-step завершён.
            self.pet.animator.notify_motion_complete()
            return

        self.ctx.walk_target_x = target_x
        self.ctx.is_walking = True

    def start_run_to_x(self, target_x: int):
        """
        Запускает движение к конкретной X-координате.

        ВАЖНО:
        Этот метод больше не включает RUNNING анимацию сам.
        RUNNING должен уже быть активирован sequence-логикой через PetAnimator.
        """
        current_x = self.pet.x()
        target_x, _ = self.pet.clamp_position(target_x, self.pet.ground_y)

        if target_x == current_x:
            self.pet.animator.notify_motion_complete()
            return

        direction = 1 if target_x > current_x else -1
        self.ctx.walk_direction = direction
        self.ctx.walk_target_x = target_x
        self.ctx.is_walking = True

        self.pet.set_facing_right(direction == 1)

    def get_tray_target_x(self):
        screen_rect = self.pet.get_current_screen_rect()
        margin = 40
        return screen_rect.x() + screen_rect.width() - self.pet.width() - margin

    def process_walk_step(self):
        if not self.ctx.is_walking or self.ctx.is_dragging:
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
        """
        Falling в новой архитектуре — это interrupt.
        После приземления мы не ставим анимацию вручную,
        а просим аниматор завершить interrupt через recovery sequence:
            FALLING -> FALLING_RECOVERY -> STANDING_IDLE
        """
        self.ctx.is_recovering = True

        if hasattr(self.pet, "resolve_animation_interrupt"):
            self.pet.resolve_animation_interrupt()
        else:
            self.pet.animator.resolve_interrupt()

    def finish_fall_recovery(self):
        """
        Здесь больше не переключаем анимацию вручную.
        К этому моменту PetAnimator уже должен был пройти recovery sequence.
        """
        self.ctx.is_recovering = False

    def stop_horizontal_motion(self):
        """
        Немедленно останавливает текущий walk/run сегмент.
        """
        self.ctx.is_walking = False
        self.ctx.walk_target_x = self.pet.x()