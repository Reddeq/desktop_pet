from enum import Enum


class AnimationClip(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    FALLING = "falling"
    FALLING_RECOVERY = "falling_recovery"
    CLEANING = "cleaning"
    ALERT = "alert"
    RUN = "run"
    DIG = "dig"
    SWAT = "swat"
    SLEEP_ENTER = "sleep_enter"
    SLEEP_LOOP = "sleep_loop"
    SLEEP_EXIT = "sleep_exit"
