import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "zoomies"
    flags = ("is_post_pooping_zoomies",)
    interruptible_by_needs = False

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
        self.phase = "running"
        self.play(AnimationNode.RUNNING, PetState.RUN)
        self.motion.start_run_to_x(target)

    def on_tick(self):
        if (self.phase == "running" and not self.ctx.is_walking
                and self.pet.current_animation_node() == AnimationNode.RUNNING):
            self.phase = "waiting"
            self.play(AnimationNode.STANDING_IDLE)
            self.later(random.randint(250, 700), self._run)
