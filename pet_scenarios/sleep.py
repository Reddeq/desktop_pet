from pet_scenarios import BehaviorScenario
from pet_state import PetState


class Sleep(BehaviorScenario):
    name = "sleep"
    priority = True

    def can_start(self):
        return self.controller.needs.is_sleepy(self.ctx.sleep_energy_threshold)

    def is_busy(self):
        return self.ctx.is_sleeping

    def start(self):
        self.controller._reset_motion_flags()
        self.ctx.is_sleeping = True
        self.pet.set_state(PetState.SLEEP)

    def finish(self):
        self.ctx.is_sleeping = False
        self.pet.set_state(PetState.IDLE)

    def cancel(self):
        self.ctx.is_sleeping = False

    def on_needs_tick(self):
        if self.ctx.is_sleeping and self.controller.needs.values.energy >= 100.0:
            self.finish()
