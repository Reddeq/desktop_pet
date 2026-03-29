import os
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QTransform, QPainter


class AnimationPlayer(QObject):
    frame_changed = pyqtSignal(QPixmap)
    animation_finished = pyqtSignal(str)

    def __init__(
        self,
        assets_path: str,
        canvas_width: int,
        canvas_height: int,
        pet_render_height: int,
        frame_interval: int = 50,
        parent=None,
    ):
        super().__init__(parent)

        self.assets_path = Path(assets_path)
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.pet_render_height = pet_render_height

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

    def _load_frames(self, animation_name: str) -> list[QPixmap]:
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

            if animation_name in {"idle", "walk", "falling", "falling_recovery", "cleaning"} and not self.facing_right:
                pixmap = pixmap.transformed(
                    QTransform().scale(-1, 1),
                    Qt.TransformationMode.SmoothTransformation,
                )

            scaled_pixmap = pixmap.scaledToHeight(
                self.pet_render_height,
                Qt.TransformationMode.SmoothTransformation,
            )

            canvas = QPixmap(self.canvas_width, self.canvas_height)
            canvas.fill(Qt.GlobalColor.transparent)

            painter = QPainter(canvas)

            x = (self.canvas_width - scaled_pixmap.width()) // 2
            y = self.canvas_height - scaled_pixmap.height()

            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()

            frames.append(canvas)

        return frames