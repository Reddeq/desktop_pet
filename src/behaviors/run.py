import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "run"
    flags = ("is_post_poop_run",)

    def on_start(self):
        self.later(random.randint(10_000, 20_000), self.finish)
        self._run()

    def _run(self):
        screen = self.pet.get_current_screen_rect()
        left = screen.x() + 20
        right = max(left, screen.x() + screen.width() - self.pet.width() - 20)
        target = random.randint(left, right)
        if abs(target - self.pet.x()) < 40:
            target = left if self.pet.x() > (left + right) // 2 else right
        self.phase = "run"
        self.play(AnimationNode.RUN, PetState.RUN)
        self.motion.start_run_to_x(target)

    def on_tick(self):
        if (self.phase == "run" and not self.ctx.is_walk
                and self.pet.current_animation_node() == AnimationNode.RUN):
            self.phase = "wait"
            self.play(AnimationNode.STAND_IDLE)
            self.later(random.randint(250, 700), self._run)
