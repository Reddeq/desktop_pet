from pathlib import Path

from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtCore import Qt

from interaction_mode import InteractionMode


class InteractionCursorManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.mode = InteractionMode.GRAB

        self.grab_cursor = QCursor(Qt.CursorShape.OpenHandCursor)
        self.grab_drag_cursor = QCursor(Qt.CursorShape.ClosedHandCursor)

        feed_cursor_path = self.base_dir / "assets" / "cursors" / "meat_cursor.png"
        if feed_cursor_path.exists():
            self.feed_cursor = QCursor(QPixmap(str(feed_cursor_path)), 0, 0)
        else:
            self.feed_cursor = QCursor(Qt.CursorShape.PointingHandCursor)


    def cycle_mode(self, direction: int):
        modes = [
            InteractionMode.GRAB,
            InteractionMode.FEED,
        ]

        current_index = modes.index(self.mode)
        new_index = (current_index + direction) % len(modes)
        self.mode = modes[new_index]

    def current_mode(self) -> InteractionMode:
        return self.mode

    def set_mode(self, mode: InteractionMode):
        self.mode = mode


    def get_current_cursor(self) -> QCursor:
        if self.mode == InteractionMode.FEED:
            return self.feed_cursor

        return self.grab_cursor

    def get_drag_cursor(self) -> QCursor:
        return self.grab_drag_cursor


    def is_cursor_over_widget(self, widget) -> bool:
        global_pos = QCursor.pos()
        local_pos = widget.mapFromGlobal(global_pos)
        return widget.rect().contains(local_pos)

    def apply_to_widget(self, widget):
        if self.is_cursor_over_widget(widget):
            widget.setCursor(self.get_current_cursor())
        else:
            widget.unsetCursor()

    def clear_from_widget(self, widget):
        widget.unsetCursor()