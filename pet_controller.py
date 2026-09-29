from PyQt6.QtCore import QObject, QTimer

from pet_behavior import PetBehavior
from pet_context import PetContext
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
        self.needs_timer = QTimer(self)
        self.needs_timer.timeout.connect(self._on_needs_tick)

        self.motion = PetMotion(controller=self, pet=pet, ctx=self.ctx, parent=self)
        self.needs = PetNeeds(parent=self)
        self.behavior = PetBehavior(self)

    def start(self):
        self.logic_timer.start(5000)
        self.gravity_timer.start(20)
        self.walk_timer.start(16)
        self.needs_timer.start(1000)
        self.behavior.start()

    def stop(self):
        self.logic_timer.stop()
        self.gravity_timer.stop()
        self.walk_timer.stop()
        self.needs_timer.stop()
        self.behavior.stop()

    def _on_logic_tick(self):
        self.behavior.tick()

    def _on_needs_tick(self):
        self.needs.tick(self.pet.current_state)
        self.behavior.on_needs_tick()

    def on_animation_finished(self, animation_name: str):
        if animation_name == PetState.FALLING_RECOVERY.value and self.ctx.is_recovering:
            self.motion.finish_fall_recovery()
        self.behavior.on_animation_finished(animation_name)

    def _reset_motion_flags(self):
        self.ctx.is_falling = False
        self.ctx.gravity_speed = 0
        self.ctx.is_walking = False
        self.ctx.is_recovering = False
        self.behavior.cancel()

    def feed(self):
        self.needs.feed()

    def use_toilet(self):
        self.needs.use_toilet()

    # Public commands used by the UI; implementations live with their scenarios.
    def start_sleep(self):
        self.behavior.by_name['sleep'].start()

    def finish_sleep(self):
        self.behavior.by_name['sleep'].finish()

    def start_notification_investigation(self):
        self.behavior.by_name['notifications'].start()

    def go_to_notification_area(self):
        self.behavior.by_name['notifications'].go_to_area()

    def start_dig(self):
        self.behavior.by_name['notifications'].start_dig()

    def finish_notification_investigation(self):
        self.behavior.by_name['notifications'].finish()

    def start_cleaning(self):
        self.behavior.by_name['cleaning'].start()

    def finish_cleaning(self):
        self.behavior.by_name['cleaning'].finish()

    def process_walk_step(self):
        if not self.behavior.by_name['cursor'].process_chase_step():
            self.motion.process_walk_step()

    def apply_gravity(self):
        self.motion.apply_gravity()

    def on_mouse_press(self, global_pos):
        self.behavior.by_name['drag'].press(global_pos)

    def on_mouse_move(self, global_pos):
        self.behavior.by_name['drag'].move(global_pos)

    def on_mouse_release(self):
        self.behavior.by_name['drag'].release()
