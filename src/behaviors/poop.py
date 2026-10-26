import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "poop"
    requires_desktop = True
    flags = ("is_poop",)
    priority = 200
    retry_seconds = 30

    def on_start(self):
        self.dig_finish_pending = False
        self.poop_finish_pending = False
        screen = self.pet.get_current_screen_rect()
        left = screen.x() + 20
        right = max(left, screen.x() + screen.width() - self.pet.width() - 20)
        self.phase = "run"
        self.play(AnimationNode.RUN, PetState.RUN)
        self.motion.start_run_to_x(random.choice([left, right]))

    def on_tick(self):
        node = self.pet.current_animation_node()
        if self.phase == "run" and node == AnimationNode.RUN and not self.ctx.is_walk:
            self.phase = "poop_transition"
            self.play(AnimationNode.POOP)
        elif self.phase == "poop_transition" and node == AnimationNode.POOP:
            self.phase = "poop"
            self.later(5000, self._request_finish_poop)
        elif self.phase == "dig_transition" and node == AnimationNode.DIG:
            self.phase = "dig"
            self.later(random.randint(1500, 2500), self._request_finish_dig)

    def _request_finish_dig(self):
        self.dig_finish_pending = True

    def _request_finish_poop(self):
        self.poop_finish_pending = True

    def on_animation_loop_finished(self, node):
        if (node == AnimationNode.POOP and self.phase == "poop"
                and self.poop_finish_pending):
            self.phase = "poop_end"
            self.play(AnimationNode.END_POOP)
        if (node == AnimationNode.DIG and self.phase == "dig"
                and self.dig_finish_pending):
            self.phase = "dig_end"
            self.play(AnimationNode.END_DIG, PetState.DIG)

    def on_animation_finished(self, node):
        if node == AnimationNode.END_POOP and self.phase == "poop_end":
            self._dig()
        if node == AnimationNode.END_DIG and self.phase == "dig_end":
            self._run()

    def _dig(self):
        self.phase = "dig_transition"
        self.play(AnimationNode.DIG, PetState.DIG)

    def _run(self):
        self.manager.start("run")
