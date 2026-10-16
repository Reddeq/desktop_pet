"""Playback clock. Asset decoding and rendering live in animation_assets."""
import logging
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from animation_assets import AnimationAssets, AssetError, positive_int


class AnimationPlayer(QObject):
    frame_changed = pyqtSignal(QPixmap)
    animation_finished = pyqtSignal(str)
    animation_loop_finished = pyqtSignal(str)

    def __init__(self, assets_path: str, scale_factor: float = 0.5,
                 frame_interval: int = 50, parent=None):
        super().__init__(parent)
        self.assets_path = Path(assets_path)
        self.assets = AnimationAssets(assets_path, scale_factor, frame_interval)
        self.current_animation = None
        self.current_frame_index = 0
        self.frames = []
        self._durations = ()
        self.facing_right = True
        self.current_loop = True
        self._finished_emitted = False
        self.last_error = None
        self._playback_generation = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(frame_interval)
        self.timer.timeout.connect(self._next_frame)

    def set_frame_interval(self, interval_ms: int):
        self.assets.interval = positive_int(interval_ms, "frame interval")
        self.assets.clear_cache()
        self.timer.setInterval(interval_ms)
        if self.current_animation is not None:
            self.set_animation(self.current_animation, self.current_loop, force=True)

    def frame_interval(self) -> int:
        return self.timer.interval()

    def has_frames(self) -> bool:
        return bool(self.frames)

    def duration_ms(self) -> int:
        return sum(self._durations) if self._durations else len(self.frames) * self.assets.interval

    def set_facing_right(self, value: bool):
        if self.facing_right == value:
            return
        self.facing_right = value
        if self.current_animation is not None and self.frames:
            frames = self._load_frames(self.current_animation)
            if frames:
                self.frames = frames
                self.frame_changed.emit(self.frames[self.current_frame_index])

    def set_animation(self, animation_name: str, loop: bool, force: bool = False) -> bool:
        if not force and self.current_animation == animation_name and self.current_loop == loop:
            return bool(self.frames)
        self.timer.stop()
        self._playback_generation += 1
        self.current_animation = animation_name
        self.current_loop = loop
        self.current_frame_index = 0
        self._finished_emitted = False
        self._durations = ()
        self.frames = self._load_frames(animation_name)
        if not self.frames:
            return False
        self._schedule_frame()
        self.frame_changed.emit(self.frames[0])
        return True

    def _schedule_frame(self):
        duration = self._durations[self.current_frame_index] if self._durations else self.assets.interval
        self.timer.start(duration)

    def _next_frame(self):
        if not self.frames or self._finished_emitted:
            return
        if self.current_frame_index == len(self.frames) - 1:
            if not self.current_loop:
                self.timer.stop()
                self._finished_emitted = True
                self.animation_finished.emit(self.current_animation)
                return  # A finish listener may have started the next clip.
            generation = self._playback_generation
            self.animation_loop_finished.emit(self.current_animation)
            if generation != self._playback_generation:
                return  # A loop listener has started an exit transition.
            self.current_frame_index = 0
        else:
            self.current_frame_index += 1
        self._schedule_frame()
        self.frame_changed.emit(self.frames[self.current_frame_index])

    def _load_frames(self, animation_name):
        try:
            clip = self.assets.load(animation_name, self.facing_right)
        except (AssetError, OSError) as exc:
            self.last_error = str(exc)
            logging.getLogger(__name__).error("Animation %s: %s", animation_name, exc)
            return []
        self.last_error = None
        self._durations = clip.durations_ms
        return list(clip.frames)
