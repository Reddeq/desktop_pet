from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QPoint


@dataclass
class PetContext:
    gravity_speed: int = 0

    is_fall: bool = False
    is_walk: bool = False
    is_drag: bool = False
    is_recover: bool = False
    is_clean: bool = False
    is_sleep: bool = False
    is_meow: bool = False
    is_eat: bool = False
    food_cooldown_seconds: int = 60
    is_poop: bool = False
    is_post_poop_run: bool = False
    is_hide: bool = False
    is_hidden_offscreen: bool = False
    is_menu_open: bool = False
    is_menu_forced_meow: bool = False

    is_inspect_notifications: bool = False
    is_swat_cursor: bool = False

    walk_direction: int = 1
    walk_target_x: int = 0
    walk_speed: int = 4

    cursor_front_gap: int = 18
    cursor_dead_zone: int = 10

    swat_reach_x: int = 85
    cursor_stationary_threshold: int = 8


    swat_count_in_encounter: int = 0



    is_post_swat_cautious: bool = False
    post_swat_caution_ms: int = 5000

    last_cursor_pos: Optional[QPoint] = None
    cursor_still_ticks: int = 0
    old_pos: Optional[QPoint] = None

    # -------------------------
    # Cursor sneak / swat logic
    # -------------------------
    is_hunt_cursor: bool = False
    is_wait_to_swat: bool = False

    cursor_check_interval_ms: int = 120
    cursor_stationary_ms: int = 0

    # Курсор вообще считается "интересным" для sneak,
    # если он в этой зоне по расстоянию
    cursor_hunt_distance: int = 220

    # Через сколько неподвижности начинается sneak
    cursor_hunt_start_after_ms: int = 10_000

    # Скорость sneak
    cursor_hunt_speed: int = 4
    hunt_standoff_distance: int = 90
    hunt_jump_duration_ms: int = 770
    hunt_jump_height: int = 70
    hunt_jump_max_distance: int = 280
    hunt_cursor_hold_ms: int = 1500
    hunt_capture_radius: int = 120
    hunt_dig_duration_ms: int = 2500
    hunt_cooldown_seconds: int = 60
    hunt_paw_x_ratio: float = 0.60
    hunt_paw_y_ratio: float = 0.99

    # Задержка перед swat
    swat_prepare_delay_min_ms: int = 2000
    swat_prepare_delay_max_ms: int = 3000

    # -------------------------
    # Game-like cursor resistance during swat
    # -------------------------
    swat_cursor_resist_enabled: bool = True

    # SWAT uses a moving paw target; hunt capture keeps its softer settings.
    swat_paw_dead_zone_radius: int = 3
    swat_paw_break_distance: int = 240
    swat_paw_spring_strength: float = 0.35
    swat_paw_max_pull_per_tick: float = 30.0

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
    
    is_scratch_for_food: bool = False

