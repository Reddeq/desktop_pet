import random

from animation_node import AnimationNode as N
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = 'sharpen_claws'
    interval_seconds = (180, 360)

    def on_start(self):
        self.edge = random.choice(('left', 'right'))
        self.phase = 'run'
        self.finish_pending = False
        self.play(N.RUN, PetState.RUN)
        screen = self.pet.get_current_screen_rect()
        # Place the extended front paw at the edge, not the transparent canvas.
        paw_ratio = 86.5 / 112
        if self.edge == 'right':
            target = round(screen.right() - 3 - self.pet.width() * paw_ratio)
        else:
            target = round(screen.left() + 3 - self.pet.width() * (1 - paw_ratio))
        self.motion.start_run_to_x(target, allow_partial=True)

    def on_tick(self):
        node = self.pet.current_animation_node()
        if self.phase == 'return' and node == N.RUN and not self.ctx.is_walk:
            self.finish()
            return
        if self.phase == 'run' and node == N.RUN and not self.ctx.is_walk:
            self.pet.set_facing_right(self.edge == 'right')
            self.phase = 'start'
            self.play(N.SHARPEN_CLAWS, PetState.SHARPEN_CLAWS)
        elif self.phase == 'start' and node == N.SHARPEN_CLAWS:
            self.phase = 'loop'
            self.later(random.randint(4000, 8000), self._request_finish)

    def _request_finish(self):
        self.finish_pending = True

    def on_animation_loop_finished(self, node):
        if node == N.SHARPEN_CLAWS and self.phase == 'loop' and self.finish_pending:
            self.phase = 'end'
            self.play(N.END_SHARPEN_CLAWS, PetState.SHARPEN_CLAWS)

    def on_animation_finished(self, node):
        if node == N.END_SHARPEN_CLAWS and self.phase == 'end':
            self.phase = 'return'
            self.play(N.RUN, PetState.RUN)
            target, _ = self.pet.clamp_position(self.pet.x(), self.pet.ground_y)
            self.motion.start_run_to_x(target)
