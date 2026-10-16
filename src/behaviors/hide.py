import random

from animation_node import AnimationNode
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = "hide"
    flags = ("is_hide", "is_hidden_offscreen")
    priority = 80
    preserve_on_menu = True
    interval_seconds = (180, 360)

    def on_start(self):
        self.ctx.is_hidden_offscreen = False
        self.edge = random.choice(["left", "right"])
        self.phase = "run"
        self.play(AnimationNode.RUN, PetState.RUN)
        self.motion.start_screen_exit(self.edge)

    def on_tick(self):
        if self.phase == "enter" and not self.ctx.is_walk:
            self.finish()
            return
        if (self.phase == "run" and not self.ctx.is_walk
                and self.pet.current_animation_node() == AnimationNode.RUN):
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
        if self.phase != "hidden":
            return
        self.phase = "start"
        self.ctx.is_hidden_offscreen = False
        self.pet.set_horizontal_edge_anchor(self.edge)
        self._place()
        self.controller._set_logical_state(PetState.IDLE)
        self.pet.force_set_animation_node(AnimationNode.START_HIDE, hold=False)
        if self.manager.active is not self:
            return
        self.pet.play_sequence_nodes([AnimationNode.HIDE], replace=False)
        self.pet.show()

    def on_animation_finished(self, node):
        if node == AnimationNode.START_HIDE and self.phase == "start":
            self.phase = "hide"
            # Count the watching time only after the entry has fully played.
            self.later(random.randint(5000, 10_000), self._leave)
        elif node == AnimationNode.END_HIDE and self.phase == "end":
            self.phase = "return"
            self.ctx.is_hidden_offscreen = True
            self.pet.hide()
            self.pet.animator.clear()
            self.later(random.randint(1000, 2000), self._return_to_ground)

    def _leave(self):
        if self.phase != "hide":
            return
        self.phase = "end"
        self.play(AnimationNode.END_HIDE)

    def _return_to_ground(self):
        if self.phase != "return":
            return
        self.ctx.is_hidden_offscreen = False
        self.phase = "enter"
        if not self.motion.start_screen_entry(self.edge) and self.manager.active is self:
            self.finish()

    def on_stop(self):
        self.pet.set_horizontal_edge_anchor(None)
        x, y = self.pet.clamp_position(self.pet.x(), self.pet.y())
        self.pet.move(x, y)
        if not self.pet.isVisible():
            self.pet.show()
