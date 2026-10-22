"""One cancellable platform transfer, driven by the existing movement tick."""
from animation_node import AnimationNode as N
from jump_trajectory import JumpTrajectory, flight_progress
from pet_state import PetState


class SurfaceTravel:
    def __init__(self, surfaces):
        self.surfaces = surfaces
        self.controller = surfaces.controller
        self.pet = surfaces.pet
        self.phase = None
        self.after_behavior = None

    @property
    def active(self):
        return self.phase is not None

    def cancel(self):
        self.phase = None
        self.after_behavior = None

    def begin(self, plan, after_behavior=None):
        self.controller._reset_motion_flags()
        self.plan = plan
        self.after_behavior = after_behavior
        self.phase = 'approach'
        self.pet.play_node(N.WALK, replace=True, force_restart=True)
        if self.phase != 'approach':
            return False  # A synchronous asset failure may have started a fall.
        self.controller.motion.start_run_to_x(round(plan.launch_x))
        return True

    def tick(self, now):
        if self.phase == 'approach':
            self.controller.motion.process_walk_step()
            if not self.controller.ctx.is_walk and self.pet.current_animation_node() == N.WALK:
                self._launch(now)
        elif self.phase == 'jump':
            t = flight_progress((now - self.started) / self.duration)
            x, foot = self.trajectory.position(t)
            self.pet.move(round(x), round(foot - self.pet.height()))
            if t >= 1 and self.finished:
                self._land()

    def _launch(self, now):
        self.surfaces.refresh()
        target = self.surfaces.by_id(self.plan.target)
        if target is None:
            self.cancel()
            self.controller.start_idle()
            return
        end_x = target.clamp_x(self.plan.landing_x, self.pet.width())
        cfg = self.surfaces.config
        rise = self.pet.y() + self.pet.height() - target.y
        if (abs(end_x - self.pet.x()) > cfg.max_distance or rise > cfg.max_rise
                or target.right - target.left < self.pet.width() + 2 * cfg.landing_margin):
            self.cancel()
            self.controller.start_idle()
            return
        self.trajectory = JumpTrajectory(self.pet.x(), self.pet.y() + self.pet.height(),
                                         end_x, target.y, self.plan.trajectory.height)
        if not self.surfaces.clear_jump(self.trajectory, target):
            self.cancel()
            self.controller.start_idle()
            return
        self.phase = 'jump'
        self.started = now
        self.finished = False
        self.pet.set_facing_right(end_x >= self.pet.x())
        self.controller._set_logical_state(PetState.JUMP)
        self.pet.force_set_animation_node(N.JUMP, hold=False)
        player = self.pet.animation_player
        self.duration = (player.duration_ms() if hasattr(player, 'duration_ms')
                         else self.surfaces.config.jump_duration_ms) / 1000

    def animation_finished(self, node):
        if self.phase == 'jump' and node == N.JUMP:
            self.finished = True

    def revalidate(self):
        if self.phase != 'jump':
            return
        target = self.surfaces.by_id(self.plan.target)
        if target is None or not target.fits(self.trajectory.end_x, self.pet.width()):
            self.surfaces.fall()
            return
        if target.y != self.trajectory.end_y or not self.surfaces.clear_jump(self.trajectory, target):
            # Never snap to a moved destination or finish an obsolete route.
            self.surfaces.fall()

    def _land(self):
        self.surfaces.refresh()
        if self.phase != 'jump':
            return
        target = self.surfaces.by_id(self.plan.target)
        if target is None:
            self.surfaces.fall()
            return
        after_behavior = self.after_behavior
        self.cancel()
        self.pet.move(round(self.trajectory.end_x), round(target.y - self.pet.height()))
        self.surfaces.attach(target)
        self.controller.start_idle()
        self.surfaces.after_transfer()
        if after_behavior is not None and target.kind == 'desktop':
            self.controller.start_behavior(after_behavior)
