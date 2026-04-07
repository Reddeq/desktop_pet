import random

from PyQt6.QtCore import QObject

from animation_node import AnimationNode
from pet_state import PetState


class PetBehavior(QObject):
    def __init__(self, controller, pet, ctx, motion, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.pet = pet
        self.ctx = ctx
        self.motion = motion

    # -------------------------
    # Busy / gate checks
    # -------------------------

    def is_busy(self) -> bool:
        return (
            self.ctx.is_falling
            or self.ctx.is_walking
            or self.ctx.is_dragging
            or self.ctx.is_recovering
            or self.ctx.is_cleaning
            or self.ctx.is_sleeping
            or self.ctx.is_investigating_notifications
            or self.ctx.is_hunting_cursor
            or self.ctx.is_waiting_to_swat
            or self.ctx.is_swatting_cursor
            or self.ctx.is_scratching_for_food
            or self.ctx.is_eating
            or self.ctx.is_pooping
            or self.ctx.is_post_pooping_zoomies
            or self.ctx.is_hiding
            or self.ctx.is_menu_open
            or self.ctx.is_menu_forced_meowing

        )

    # -------------------------
    # Autonomous scenarios
    # -------------------------

    def start_walk_scenario(self):
        """
        Случайное блуждание:
        - сначала проверяем, возможно ли реальное движение;
        - только потом запускаем animation sequence.
        """
        direction = random.choice([-1, 1])
        distance = random.randint(60, 180)

        if not self.motion.start_walk(direction, distance):
            self.controller.start_idle()
            return

        self.controller._set_logical_state(PetState.WALK)

        self.pet.play_sequence_nodes(
            [
                AnimationNode.WALKING,
                AnimationNode.SITTING_IDLE,
            ],
            replace=True,
            force_restart=True,
        )

    def start_idle_scenario(self):
        """
        Возврат в обычную сидячую idle-позу.
        """
        self.controller.start_idle()

    # -------------------------
    # Main tick
    # -------------------------

    def tick(self):
        if self.ctx.is_sleeping:
            return

        if self.is_busy():
            return

        if self.controller.needs.is_sleepy(self.ctx.sleep_energy_threshold):
            self.controller.start_sleep()
            return

        if random.random() < self.ctx.hiding_trigger_chance:
            self.controller.start_hiding_sequence()
            return

        # begging for food if satiety < 50
        begging_chance = self._food_begging_chance()
        if begging_chance > 0.0 and random.random() < begging_chance:
            self.controller.start_scratching_for_food()
            return

        
        mood = self.controller.needs.values.mood

        if mood < 50.0:
            actions = [
                "idle",
                "walk",
                "cleaning",
                "meowing",
            ]
            weights = [0.45, 0.25, 0.20, 0.10]
        else:
            actions = [
                "idle",
                "walk",
                "cleaning",
                "investigate_notifications",
            ]
            weights = [0.45, 0.25, 0.20, 0.10]
        new_action = random.choices(actions, weights=weights)[0]

        if new_action == "walk":
            self.start_walk_scenario()

        elif new_action == "cleaning":
            self.controller.start_cleaning()

        elif new_action == "investigate_notifications":
            self.controller.start_notification_investigation()

        elif new_action == "meowing":
            self.controller.start_meowing()

        else:
            self.start_idle_scenario()



    def _food_begging_chance(self) -> float:
        satiety = self.controller.needs.values.satiety
        threshold = self.ctx.food_begging_satiety_threshold

        if satiety >= threshold:
            return 0.0

        # 50 -> 0.05, 0 -> 0.40
        return 0.05 + ((threshold - satiety) / threshold) * 0.35