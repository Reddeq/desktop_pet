from pet_scenarios import BehaviorScenario
from pet_state import PetState


class Idle(BehaviorScenario):
    name = "idle"
    weight = 0.45

    def start(self):
        self.pet.set_state(PetState.IDLE)
