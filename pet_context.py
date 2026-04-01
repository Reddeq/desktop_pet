from dataclasses import dataclass, field
from typing import Optional
from random import randint

from PyQt6.QtCore import QPoint


@dataclass
class PetContext:
    gravity_speed: int = 0

    is_falling: bool = False
    is_walking: bool = False
    is_dragging: bool = False
    is_recovering: bool = False
    is_cleaning: bool = False
    is_sleeping: bool = False

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

    swat_release_margin_x: int = 18
    swat_release_margin_y: int = 12

    swat_count_in_encounter: int = 0
    max_swats_per_encounter: int = 2

    swat_timeout_ms: int = field(default_factory=lambda: randint(3, 10) * 1000)

    cursor_chase_trigger_chance: float = 0.25
    post_swat_trigger_chance: float = 0.07

    is_post_swat_cautious: bool = False
    post_swat_caution_ms: int = 5000

    sleep_energy_threshold: float = 20.0

    last_cursor_pos: Optional[QPoint] = None
    cursor_still_ticks: int = 0
    old_pos: Optional[QPoint] = None

    # -------------------------
    # Game-like cursor resistance during swat
    # -------------------------
    swat_cursor_resist_enabled: bool = True

    # Частота обновления сопротивления
    swat_cursor_resist_interval_ms: int = 16

    # Радиус мёртвой зоны вокруг лапы — внутри неё курсор не тянем
    swat_cursor_dead_zone_radius: int = 18

    # "Жёсткость пружины": насколько сильно тянем назад
    swat_cursor_spring_strength: float = 0.18

    # Демпфирование: чем меньше, тем сильнее вязкость / меньше разлёт
    swat_cursor_damping: float = 0.72

    # Ограничение максимального сдвига курсора за один тик
    swat_cursor_max_pull_per_tick: float = 10.0

    # Если пользователь слишком сильно дёрнул курсор —
    # сопротивление временно ослабевает / отпускает
    swat_cursor_break_distance: int = 120