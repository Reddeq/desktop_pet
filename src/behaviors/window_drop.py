"""Leave through a side edge, then reveal FALL from above a window."""
import random

from PyQt6.QtCore import QRect
from animation_node import AnimationNode as N
from behavior_runtime import Scenario
from pet_state import PetState


class Behavior(Scenario):
    id = 'window_drop'
    requires_desktop = True
    preserve_on_menu = True
    interval_seconds = (240, 420)  # hide uses 180–360 seconds.
    priority = 75

    @classmethod
    def can_start(cls, controller):
        surfaces = controller.surfaces
        return (surfaces.enabled and not surfaces.elevated
                and not controller.interaction_locked
                and abs(controller.pet.y() + controller.pet.height() - surfaces.desktop().y) <= 2
                and bool(surfaces.top_entries()))

    def on_start(self):
        self.phase = 'run'
        self.edge = random.choice(('left', 'right'))
        self.play(N.RUN, PetState.RUN)
        self.motion.start_screen_exit(self.edge)

    def on_tick(self):
        if self.phase == 'run' and not self.ctx.is_walk and self.pet.current_animation_node() == N.RUN:
            self.phase = 'hidden'
            self.ctx.is_hidden_offscreen = True
            self.later(random.randint(400, 900), self._drop)
        elif self.phase == 'return' and not self.ctx.is_walk:
            self.finish()
        elif self.phase == 'fall' and not self.controller.surfaces.enabled:
            self.finish(go_idle=False)
            if self.ctx.is_fall:
                self.controller.surfaces.prepare_drop()

    def _drop(self):
        surfaces = self.controller.surfaces
        if surfaces.enabled:
            surfaces.refresh()
        entries = surfaces.top_entries() if surfaces.enabled else ()
        if not entries:
            self.phase = 'return'
            self.ctx.is_hidden_offscreen = False
            if not self.motion.start_screen_entry(self.edge):
                self.finish()
            return
        entry = random.choice(entries)
        monitor = next(m for m in surfaces.monitors if m.id == entry.platform.monitor)
        self.phase = 'fall'
        surfaces.detach()
        surfaces.fall_target = entry.platform
        self.ctx.is_fall = True
        self.ctx.gravity_speed = 0
        self.ctx.is_hidden_offscreen = False
        self.pet.ground_y = round(entry.platform.y - self.pet.height())
        clip = monitor.logical
        self.pet.set_screen_clip(QRect(round(clip.left), round(clip.top),
                                       round(clip.width), round(clip.height)))
        self.pet.move(round(entry.x), round(entry.top - self.pet.height()))
        self.controller._set_logical_state(PetState.FALL)
        self.pet.interrupt_animation(N.FALL, recovery_targets=[N.RECOVER, N.STAND_IDLE])
        if self.manager.active is self:
            self.pet.show()

    def on_animation_finished(self, node):
        if node == N.RECOVER and self.phase == 'fall':
            self.finish()

    def on_stop(self):
        self.pet.set_screen_clip(None)
        self.ctx.is_hidden_offscreen = False
        if self.phase in {'run', 'hidden', 'return'}:
            x, y = self.pet.clamp_position(self.pet.x(), self.pet.ground_y)
            self.pet.move(x, y)
            self.pet.show()
