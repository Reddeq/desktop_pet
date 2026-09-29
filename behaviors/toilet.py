import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "toilet"
    flags = ("is_pooping",)
    priority = 200
    interruptible_by_needs = False

    @classmethod
    def probability(cls, controller, event):
        return float(event == "needs" and controller.needs.values.bladder <= controller.ctx.poop_bladder_threshold)

    def on_start(self):
        screen = self.pet.get_current_screen_rect()
        left = screen.x() + 20
        right = max(left, screen.x() + screen.width() - self.pet.width() - 20)
        self.phase = "running"
        self.play(AnimationNode.RUNNING, PetState.RUN)
        self.motion.start_run_to_x(random.choice([left, right]))

    def on_tick(self):
        node = self.pet.current_animation_node()
        if self.phase == "running" and node == AnimationNode.RUNNING and not self.ctx.is_walking:
            self.phase = "pooping_transition"
            self.play(AnimationNode.POOPING)
        elif self.phase == "pooping_transition" and node == AnimationNode.POOPING:
            self.phase = "pooping"
            self.later(random.randint(2000, 4000), self._dig)
        elif self.phase == "digging_transition" and node == AnimationNode.DIGGING:
            self.phase = "digging"
            self.later(random.randint(1500, 2500), self._zoomies)

    def _dig(self):
        self.needs.use_toilet()
        self.phase = "digging_transition"
        self.play(AnimationNode.DIGGING, PetState.DIG)

    def _zoomies(self):
        self.manager.start("zoomies")
