from behavior_runtime import Scenario


class Behavior(Scenario):
    id = "idle"

    @classmethod
    def weight(cls, controller):
        return 0.45

    def on_start(self):
        self.finish()
