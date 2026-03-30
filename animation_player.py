import os
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QTransform


class AnimationPlayer(QObject):
    frame_changed = pyqtSignal(QPixmap)
    animation_finished = pyqtSignal(str)

    def __init__(
        self,
        assets_path: str,
        scale_factor: float = 0.5,
        frame_interval: int = 50,
        parent=None,
    ):
        super().__init__(parent)

        self.assets_path = Path(assets_path)
        self.scale_factor = scale_factor

        self.current_animation = None
        self.current_frame_index = 0
        self.frames = []
        self.facing_right = True

        self.loop_map = {
            "idle": True,
            "walk": True,
            "falling": True,
            "falling_recovery": False,
            "cleaning": True,
            "alert": False,
            "run": True,
            "dig": True,
            "swat": True,
            "sleep": True,
        }

        self._finished_emitted = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)
        self.timer.start(frame_interval)

    def set_frame_interval(self, interval_ms: int):
        self.timer.setInterval(interval_ms)

    def frame_interval(self) -> int:
        return self.timer.interval()

    def has_frames(self) -> bool:
        return bool(self.frames)

    def set_facing_right(self, value: bool):
        if self.facing_right != value:
            self.facing_right = value
            if self.current_animation is not None:
                self.set_animation(self.current_animation, force=True)

    def set_animation(self, animation_name: str, force: bool = False) -> bool:
        if not force and self.current_animation == animation_name:
            return bool(self.frames)

        self.current_animation = animation_name
        self.current_frame_index = 0
        self._finished_emitted = False
        self.frames = self._load_frames(animation_name)

        if self.frames:
            self.frame_changed.emit(self.frames[0])
            return True

        return False

    def _is_looping(self, animation_name: str) -> bool:
        return self.loop_map.get(animation_name, True)

    def _next_frame(self):
        if not self.frames:
            return

        if len(self.frames) == 1:
            self.frame_changed.emit(self.frames[0])

            if not self._is_looping(self.current_animation) and not self._finished_emitted:
                self._finished_emitted = True
                self.animation_finished.emit(self.current_animation)
            return

        if self._is_looping(self.current_animation):
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
            self.frame_changed.emit(self.frames[self.current_frame_index])
            return

        if self.current_frame_index < len(self.frames) - 1:
            self.current_frame_index += 1
            self.frame_changed.emit(self.frames[self.current_frame_index])
        else:
            self.frame_changed.emit(self.frames[self.current_frame_index])

            if not self._finished_emitted:
                self._finished_emitted = True
                self.animation_finished.emit(self.current_animation)

    def _load_frames(self, animation_name: str) -> list:
        frames = []
        path = self.assets_path / animation_name

        if not path.exists():
            return frames

        files = sorted([f for f in os.listdir(path) if f.endswith(".png")])

        for file_name in files:
            full_path = path / file_name
            pixmap = QPixmap(str(full_path))

            if pixmap.isNull():
                continue

            if animation_name in {
                "idle",
                "walk",
                "falling",
                "falling_recovery",
                "cleaning",
                "alert",
                "run",
                "dig",
                "swat",
                "sleep",
            } and not self.facing_right:
                pixmap = pixmap.transformed(
                    QTransform().scale(-1, 1),
                    Qt.TransformationMode.SmoothTransformation,
                )

            new_width = max(1, int(pixmap.width() * self.scale_factor))
            new_height = max(1, int(pixmap.height() * self.scale_factor))

            scaled_pixmap = pixmap.scaled(
                new_width,
                new_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            frames.append(scaled_pixmap)

        return frames