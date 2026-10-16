"""Actual Qt window clipping, including the border between two monitors."""
import unittest
from unittest.mock import patch

from test_behaviors import APP
from app import FrameAnimatedPet
from PyQt6.QtCore import QRect


class ScreenEntryTests(unittest.TestCase):
    def setUp(self):
        with patch('pet_motion.random.choice', return_value='left'):
            self.pet = FrameAnimatedPet()
        self.controller = self.pet.controller
        for timer in (self.controller.logic_timer, self.controller.gravity_timer,
                      self.controller.walk_timer, self.controller.cursor_ai.cursor_check_timer):
            timer.stop()

    def tearDown(self):
        self.controller.stop()
        self.pet.debug_console.stop()
        self.pet.close()
        self.pet.deleteLater()
        APP.processEvents()

    def test_startup_begins_outside_then_reveals_part_of_window(self):
        screen = self.pet.get_current_screen_rect()
        self.assertEqual(self.controller.behaviors.active.id, 'enter')
        self.assertFalse(self.pet.geometry().intersects(screen))
        self.assertFalse(self.pet.mask().intersects(self.pet.rect()))
        visible_widths = []
        for _ in range(500):
            self.controller.process_walk_step()
            visible_widths.append(self.pet.geometry().intersected(screen).width())
            if self.controller.behaviors.active is None:
                break
        self.assertTrue(any(0 < width < self.pet.width() for width in visible_widths))
        self.assertIsNone(self.controller.behaviors.active)
        self.assertTrue(self.pet.mask().isEmpty())
        self.assertTrue(screen.contains(self.pet.geometry()))

    def test_mask_keeps_adjacent_monitor_hidden_on_either_side(self):
        self.controller.stop()
        # A monitor with negative origin: geometry on its neighboring monitor
        # must remain invisible even though the desktop itself continues there.
        screen = QRect(-800, -500, 800, 800)
        width, height = self.pet.width(), self.pet.height()
        self.pet.set_screen_clip(screen)
        for x, expected in ((screen.left() - width // 2, QRect(width // 2, 0, width // 2, height)),
                            (screen.right() + 1 - width // 2, QRect(0, 0, width // 2, height))):
            self.pet.move(x, screen.bottom() + 1 - height)
            self.assertEqual(self.pet.mask().boundingRect(), expected)
        self.pet.set_screen_clip(None)
        self.assertTrue(self.pet.mask().isEmpty())

    def test_hide_runs_fully_out_of_both_edges_before_hiding(self):
        self.controller.stop()
        screen = self.pet.get_current_screen_rect()
        for edge in ('left', 'right'):
            with self.subTest(edge=edge), patch('behaviors.hide.random.choice', return_value=edge):
                self.pet.move(screen.center().x() - self.pet.width() // 2, self.pet.ground_y)
                self.controller.behaviors.start('hide')
                scenario = self.controller.behaviors.active
                widths = []
                for _ in range(1000):
                    visible = self.pet.geometry().intersected(screen)
                    widths.append(visible.width())
                    if not visible.isEmpty():
                        self.assertTrue(self.pet.isVisible())
                    self.controller.process_walk_step()
                    if scenario.phase == 'hidden':
                        break
                self.assertEqual(scenario.phase, 'hidden')
                self.assertTrue(any(0 < width < self.pet.width() for width in widths))
                self.assertEqual(widths, sorted(widths, reverse=True))
                self.assertFalse(self.pet.geometry().intersects(screen))
                self.assertFalse(self.pet.isVisible())
                self.assertIsNone(self.pet._screen_clip)
                self.controller.behaviors.cancel()
                self.assertTrue(self.pet.isVisible())
                self.assertTrue(screen.contains(self.pet.geometry()))


if __name__ == '__main__':
    unittest.main()
