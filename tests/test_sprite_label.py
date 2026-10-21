"""Clipping must preserve pixel art and clear pixels from previous frames."""
import unittest

from test_behaviors import APP
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPixmap
from sprite_label import SpriteLabel


class SpriteLabelTests(unittest.TestCase):
    def setUp(self):
        self.label = SpriteLabel()
        self.label.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        source = QImage(12, 8, QImage.Format.Format_ARGB32)
        for y in range(source.height()):
            for x in range(source.width()):
                source.setPixelColor(x, y, QColor(x * 20, y * 30, 100))
        self.frame = source.scaled(36, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.FastTransformation)
        self.label.resize(self.frame.size())
        self.label.setPixmap(QPixmap.fromImage(self.frame))

    def tearDown(self):
        self.label.close()
        self.label.deleteLater()
        APP.processEvents()

    def render_frame(self):
        image = QImage(self.label.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor('magenta'))
        self.label.render(image)
        return image

    def test_both_edges_preserve_every_visible_pixel_without_rescaling(self):
        for clip in (QRect(17, 0, 19, 24), QRect(0, 0, 17, 24), QRect()):
            with self.subTest(clip=clip):
                self.label.set_clip_rect(clip)
                image = self.render_frame()
                for y in range(image.height()):
                    for x in range(image.width()):
                        actual = image.pixelColor(x, y)
                        if clip.contains(x, y):
                            self.assertEqual(actual, self.frame.pixelColor(x, y))
                        else:
                            self.assertEqual(actual.alpha(), 0)

    def test_shrinking_clip_and_new_frame_clear_previous_silhouette(self):
        self.render_frame()
        self.label.set_clip_rect(QRect(0, 0, 9, 24))
        image = self.render_frame()
        self.assertEqual(image.pixelColor(10, 10).alpha(), 0)
        blank = QPixmap(self.label.size())
        blank.fill(Qt.GlobalColor.transparent)
        self.label.setPixmap(blank)
        image = self.render_frame()
        self.assertTrue(all(image.pixelColor(x, y).alpha() == 0
                            for y in range(image.height()) for x in range(image.width())))
        self.label.setPixmap(QPixmap.fromImage(self.frame))
        self.label.set_clip_rect(None)
        self.assertEqual(self.render_frame(), self.frame.convertToFormat(
            QImage.Format.Format_ARGB32_Premultiplied))

