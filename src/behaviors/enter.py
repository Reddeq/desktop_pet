from behavior_runtime import Scenario


class Behavior(Scenario):
    id = 'enter'
    requires_desktop = True
    preserve_on_menu = True

    def on_start(self):
        if not self.motion.start_screen_entry():
            self.finish()

    def on_tick(self):
        if not self.ctx.is_walk:
            self.finish()
