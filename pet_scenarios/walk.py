import random
from pet_scenarios import BehaviorScenario


class Walk(BehaviorScenario):
    name = "walk"
    weight = 0.25

    def start(self):
        self.motion.start_walk(random.choice([-1, 1]), random.randint(60, 180))
