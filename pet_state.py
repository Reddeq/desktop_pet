from enum import Enum


class PetState(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    FALLING = "falling"
    FALLING_RECOVERY = "falling_recovery"
    CLEANING = "cleaning"
    ALERT = "alert"
    RUN = "run"
    DIG = "dig"
    SWAT = "swat"