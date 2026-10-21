"""Paint a whole sprite at a fixed origin, clipping without native window masks."""
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QLabel


class SpriteLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.clip_rect = None

    def set_clip_rect(self, rect):
        rect = QRect(rect) if rect is not None else None
        if rect == self.clip_rect:
            return
        self.clip_rect = rect
        self.update(self.rect())

    def paintEvent(self, event):
        painter = QPainter(self)
        # Clear the previous silhouette as the clip grows/shrinks or frames
        # change. Native regions on layered Windows windows can leave stale
        # pixels at a moving edge; the alpha buffer is the source of truth.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return
        if self.clip_rect is not None:
            painter.setClipRect(self.clip_rect)
        # Cropping must never change the sprite's origin or scale.
        painter.drawPixmap(0, 0, pixmap)
