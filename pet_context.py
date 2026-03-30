from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QPoint


@dataclass
class PetContext:
    gravity_speed: int = 0

    is_falling: bool = False
    is_walking: bool = False
    is_dragging: bool = False
    is_recovering: bool = False
    is_cleaning: bool = False

    is_investigating_notifications: bool = False
    is_chasing_cursor: bool = False
    is_swatting_cursor: bool = False

    walk_direction: int = 1
    walk_target_x: int = 0
    walk_speed: int = 4

    cursor_chase_speed: int = 6
    cursor_chase_distance: int = 160
    cursor_chase_cooldown: bool = False
    cursor_front_gap: int = 18
    cursor_dead_zone: int = 10

    swat_reach_x: int = 85
    cursor_stationary_threshold: int = 8
    cursor_stationary_ticks_required: int = 2

    last_cursor_pos: Optional[QPoint] = None
    cursor_still_ticks: int = 0

    old_pos: Optional[QPoint] = None
