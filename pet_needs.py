from dataclasses import dataclass, asdict
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from animation_node import AnimationNode
from pet_state import PetState


MAX_NEED = 100.0
MIN_NEED = 0.0


def _clamp(
    value: float,
    min_value: float = MIN_NEED,
    max_value: float = MAX_NEED,
) -> float:
    return max(min_value, min(value, max_value))


@dataclass
class NeedValues:
    satiety: float = 100.0
    energy: float = 100.0
    mood: float = 100.0
    bladder: float = 100.0


class PetNeeds(QObject):
    needs_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = NeedValues()

        # -------------------------
        # Base per-second changes
        # -------------------------
        self.satiety_decay_base = 0.04
        self.energy_decay_base = 0.03
        self.mood_decay_base = 0.02
        self.bladder_decay_base = 0.005

        # -------------------------
        # Activity modifiers
        # -------------------------
        self.satiety_activity_bonus = 0.14
        self.energy_activity_bonus = 0.12
        self.mood_activity_recovery = 0.10

        # -------------------------
        # Recovery while sleeping
        # -------------------------
        self.energy_sleep_recovery = 0.30

        # -------------------------
        # Direct action effects
        # -------------------------
        self.feed_satiety_restore = 24.0
        self.feed_bladder_penalty = 22.0
        self.swat_energy_penalty = 8.0

        # -------------------------
        # Animation-node groups
        # -------------------------
        # Более активные состояния, в которых сытость/бодрость расходуются быстрее,
        # а настроение восстанавливается
        self.active_animation_nodes = {
            AnimationNode.RUNNING,
            AnimationNode.SWATTING,
            AnimationNode.DIGGING,
            AnimationNode.HUNTING,
        }

        # Сон — отдельный режим восстановления бодрости
        self.sleep_animation_nodes = {
            AnimationNode.SLEEPING,
        }

    # -------------------------
    # Public API
    # -------------------------

    def tick(
        self,
        logical_state: Optional[PetState] = None,
        current_animation_node: Optional[AnimationNode] = None,
        delta_seconds: float = 1.0,
    ):
        """
        Один тик системы потребностей.

        Новая логика:
        - primary source: current_animation_node
        - logical_state используется только как fallback для сна,
          если animation-node по какой-то причине не передан
        """
        active_state = current_animation_node in self.active_animation_nodes

        sleeping = (
            current_animation_node in self.sleep_animation_nodes
            or logical_state == PetState.SLEEP
        )

        # -------------------------
        # Satiety
        # -------------------------
        satiety_loss = self.satiety_decay_base
        if active_state:
            satiety_loss += self.satiety_activity_bonus

        self.values.satiety = _clamp(
            self.values.satiety - satiety_loss * delta_seconds
        )

        # -------------------------
        # Energy
        # -------------------------
        if sleeping:
            self.values.energy = _clamp(
                self.values.energy + self.energy_sleep_recovery * delta_seconds
            )
        else:
            energy_loss = self.energy_decay_base
            if active_state:
                energy_loss += self.energy_activity_bonus

            self.values.energy = _clamp(
                self.values.energy - energy_loss * delta_seconds
            )

        # -------------------------
        # Mood
        # -------------------------
        if active_state:
            self.values.mood = _clamp(
                self.values.mood + self.mood_activity_recovery * delta_seconds
            )
        else:
            self.values.mood = _clamp(
                self.values.mood - self.mood_decay_base * delta_seconds
            )

        # -------------------------
        # Bladder
        # -------------------------
        self.values.bladder = _clamp(
            self.values.bladder - self.bladder_decay_base * delta_seconds
        )

        self.needs_changed.emit(self.snapshot())

    def feed(
        self,
        satiety_restore: Optional[float] = None,
        bladder_penalty: Optional[float] = None,
    ):
        satiety_restore = (
            self.feed_satiety_restore if satiety_restore is None else satiety_restore
        )
        bladder_penalty = (
            self.feed_bladder_penalty if bladder_penalty is None else bladder_penalty
        )

        self.values.satiety = _clamp(self.values.satiety + satiety_restore)
        self.values.bladder = _clamp(self.values.bladder - bladder_penalty)

        self.needs_changed.emit(self.snapshot())

    def feed_full_meal(self, bladder_penalty: float = 50.0):
        """
        Полноценное кормление:
        - сытость становится 100
        - bladder уменьшается на фиксированную величину
        """
        self.values.satiety = MAX_NEED
        self.values.bladder = _clamp(self.values.bladder - bladder_penalty)
        self.needs_changed.emit(self.snapshot())

    def apply_swat_cost(self, penalty: Optional[float] = None):
        penalty = self.swat_energy_penalty if penalty is None else penalty
        self.values.energy = _clamp(self.values.energy - penalty)
        self.needs_changed.emit(self.snapshot())

    def use_toilet(self):
        self.values.bladder = MAX_NEED
        self.needs_changed.emit(self.snapshot())

    def restore_full(self):
        self.values = NeedValues()
        self.needs_changed.emit(self.snapshot())

    def snapshot(self) -> dict:
        return asdict(self.values)

    # -------------------------
    # Convenience helpers
    # -------------------------

    def satiety_ratio(self) -> float:
        return self.values.satiety / MAX_NEED

    def energy_ratio(self) -> float:
        return self.values.energy / MAX_NEED

    def mood_ratio(self) -> float:
        return self.values.mood / MAX_NEED

    def bladder_ratio(self) -> float:
        return self.values.bladder / MAX_NEED

    def is_hungry(self, threshold: float = 35.0) -> bool:
        return self.values.satiety <= threshold

    def is_tired(self, threshold: float = 35.0) -> bool:
        return self.values.energy <= threshold

    def is_sleepy(self, threshold: float = 20.0) -> bool:
        return self.values.energy <= threshold

    def is_unhappy(self, threshold: float = 30.0) -> bool:
        return self.values.mood <= threshold

    def needs_toilet(self, threshold: float = 30.0) -> bool:
        return self.values.bladder <= threshold