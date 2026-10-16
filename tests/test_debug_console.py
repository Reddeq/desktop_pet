"""Live output must not interfere with command editing."""
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from test_behaviors import APP, N
from debug_console import DebugConsole
from pet_context_menu import PetQuickMenu
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.pet = QWidget()
        self.pet.current_animation_node = lambda: N.SLEEP
        self.controller = Mock()
        self.controller.pet = self.pet
        self.controller.behaviors = SimpleNamespace(
            active=None, registry={'sleep': object()}, errors=[],
            schedule_snapshot=lambda: {'sleep': 12},
        )
        self.pet.controller = self.controller
        self.console = DebugConsole(self.controller, self.pet)
        self.pet.debug_console = self.console
        self.console.start()

    def tearDown(self):
        self.console.stop()
        self.pet.close()
        self.pet.deleteLater()
        APP.processEvents()

    def test_hidden_by_default_menu_opens_and_reopens_same_window(self):
        self.assertIsNone(self.console.window)
        menu = PetQuickMenu(self.pet)
        self.assertEqual(menu.console_button.text(), 'Open console')
        menu.console_button.click()
        APP.processEvents()
        window = self.console.window
        self.assertTrue(window.isVisible())
        window.input.setText('run sl')
        window.close()
        self.assertFalse(window.isVisible())
        self.assertFalse(window.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose))
        menu.console_button.click()
        self.assertIs(self.console.window, window)
        self.assertEqual(window.input.text(), 'run sl')

    def test_state_output_preserves_input_selection_focus_and_command(self):
        self.console.open()
        APP.processEvents()
        entry = self.console.window.input
        entry.setText('run sleep')
        entry.setSelection(4, 3)
        self.console.log_state_change('walk')
        self.console.log_state_change('sleep')
        self.assertEqual(entry.text(), 'run sleep')
        self.assertEqual(entry.selectedText(), 'sle')
        self.assertTrue(entry.hasFocus())
        output = self.console.window.output.toPlainText()
        self.assertIn('walk | behavior idle', output)
        self.assertIn('sleep | behavior idle', output)
        entry.deselect()
        entry.setCursorPosition(len(entry.text()))
        QTest.keyClick(entry, Qt.Key.Key_Return)
        self.controller.start_behavior.assert_called_once_with('sleep')
        self.assertEqual(entry.text(), '')

    def test_commands_and_bounded_history(self):
        for i in range(600):
            self.console.write(f'line {i}')
        self.console.open()
        self.assertLessEqual(self.console.window.output.document().blockCount(), 500)
        self.assertNotIn('line 0\n', self.console.window.output.toPlainText())
        self.assertIn('line 599', self.console.window.output.toPlainText())
        for command in ('help', 'show', 'behaviors', 'schedule', 'hide', 'run', 'unknown'):
            self.console.handle_command(command)
        self.controller.debug_start_hide.assert_called_once()
        output = self.console.window.output.toPlainText()
        for expected in ('sleep | behavior idle', '12s until due', 'usage: run', 'unknown command'):
            self.assertIn(expected, output)


if __name__ == '__main__':
    unittest.main()
