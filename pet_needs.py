from dataclasses import dataclass, asdict

from PyQt6.QtCore import QObject, pyqtSignal

from pet_state import PetState


MAX_NEED = 100.0
MIN_NEED = 0.0


def _clamp(value: float, min_value: float = MIN_NEED, max_value: float = MAX_NEED) -> float:
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

        self.satiety_decay_base = 0.04
        self.energy_decay_base = 0.03
        self.mood_decay_base = 0.02
        self.bladder_decay_base = 0.005

        self.satiety_activity_bonus = 0.14
        self.energy_activity_bonus = 0.12
        self.mood_activity_recovery = 0.10

        self.energy_sleep_recovery = 0.30

        self.feed_satiety_restore = 24.0
        self.feed_bladder_penalty = 22.0

        self.swat_energy_penalty = 8.0

    def tick(self, current_state: PetState | None, delta_seconds: float = 1.0):
        active_state = current_state in {PetState.RUN, PetState.SWAT, PetState.DIG}
        sleeping = current_state == PetState.SLEEP

        satiety_loss = self.satiety_decay_base
        if active_state:
            satiety_loss += self.satiety_activity_bonus

        self.values.satiety = _clamp(
            self.values.satiety - satiety_loss * delta_seconds
        )

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

        if active_state:
            self.values.mood = _clamp(
                self.values.mood + self.mood_activity_recovery * delta_seconds
            )
        else:
            self.values.mood = _clamp(
                self.values.mood - self.mood_decay_base * delta_seconds
            )

        self.values.bladder = _clamp(
            self.values.bladder - self.bladder_decay_base * delta_seconds
        )

        self.needs_changed.emit(self.snapshot())

    def feed(self, satiety_restore: float | None = None, bladder_penalty: float | None = None):
        satiety_restore = (
            self.feed_satiety_restore if satiety_restore is None else satiety_restore
        )
        bladder_penalty = (
            self.feed_bladder_penalty if bladder_penalty is None else bladder_penalty
        )

        self.values.satiety = _clamp(self.values.satiety + satiety_restore)
        self.values.bladder = _clamp(self.values.bladder - bladder_penalty)

        self.needs_changed.emit(self.snapshot())

    def apply_swat_cost(self, penalty: float | None = None):
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