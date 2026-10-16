from enum import Enum


class PetState(str, Enum):
    IDLE = "idle"
    WALK = "walk"
    FALL = "fall"
    DRAG = "drag"
    RECOVER = "recover"
    CLEAN = "clean"
    SANDBATH = "sandbath"
    ALERT = "alert"
    RUN = "run"
    DIG = "dig"
    SWAT = "swat"
    SHARPEN_CLAWS = "sharpen_claws"
    SLEEP = "sleep"
