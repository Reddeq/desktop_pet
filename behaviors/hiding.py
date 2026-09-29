import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "hiding"
    flags = ("is_hiding", "is_hidden_offscreen")
    priority = 80
    preserve_on_menu = True

    @classmethod
    def probability(cls, controller, event):
        return controller.ctx.hiding_trigger_chance if event == "logic" else 0.0

    def on_start(self):
        self.ctx.is_hidden_offscreen = False
        screen = self.pet.get_current_screen_rect()
        self.edge = random.choice(["left", "right"])
        target = screen.x() + 10 if self.edge == "left" else screen.x() + screen.width() - self.pet.width() - 10
        self.phase = "running"
        self.play(AnimationNode.RUNNING, PetState.RUN)
        self.motion.start_run_to_x(target)

    def on_tick(self):
        if (self.phase == "running" and not self.ctx.is_walking
                and self.pet.current_animation_node() == AnimationNode.RUNNING):
            self.phase = "hidden"
            self.ctx.is_hidden_offscreen = True
            self.pet.hide()
            self.later(random.randint(3000, 6000), self._peek)

    def _place(self):
        screen = self.pet.get_current_screen_rect()
        low = screen.y() + 40
        high = max(low, screen.y() + screen.height() - self.pet.height() - 20)
        self.pet.set_facing_right(self.edge == "left")
        x = screen.x() if self.edge == "left" else screen.x() + screen.width() - self.pet.width()
        x, y = self.pet.clamp_position(x, random.randint(low, high))
        self.pet.move(x, y)

    def _peek(self):
        self.phase = "peek"
        self.ctx.is_hidden_offscreen = False
        self.pet.set_horizontal_edge_anchor(self.edge)
        self._place()
        self.controller._set_logical_state(PetState.IDLE)
        self.pet.force_set_animation_node(AnimationNode.HIDING, hold=True)
        self.pet.show()

    def on_needs(self):
        if min(self.needs.snapshot().values()) <= 0:
            if self.ctx.is_hidden_offscreen:
                self._place()
            self.finish(go_idle=False)
            self.controller.start_falling()

    def on_stop(self):
        self.pet.set_horizontal_edge_anchor(None)
        if not self.pet.isVisible():
            self.pet.show()
