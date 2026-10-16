"""On-demand console with independent command input and bounded output."""
from collections import deque
import logging

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget


class _ConsoleLogHandler(logging.Handler):
    def __init__(self, output):
        super().__init__()
        self.output = output
        self.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))

    def emit(self, record):
        self.output.emit(self.format(record))


class ConsoleWindow(QWidget):
    command_received = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle('DesktopPet Console')
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.resize(720, 420)
        layout = QVBoxLayout(self)
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(500)
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Enter a command; type 'help' for commands")
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.output)
        layout.addWidget(self.input)

    def _submit(self):
        command = self.input.text().strip()
        if command:
            self.input.clear()
            self.command_received.emit(command)


class DebugConsole(QObject):
    command_received = pyqtSignal(str)
    line_received = pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.window = None
        self._lines = deque(maxlen=500)
        self._last_logged_state_name = None
        self._log_handler = None
        self.command_received.connect(self.handle_command)
        self.line_received.connect(self.write)

    def start(self):
        if self._log_handler is None:
            self._log_handler = _ConsoleLogHandler(self.line_received)
            logging.getLogger().addHandler(self._log_handler)

    def open(self):
        if self.window is None:
            self.window = ConsoleWindow(self.controller.pet)
            self.window.command_received.connect(self.command_received.emit)
            self.window.output.setPlainText('\n'.join(self._lines))
            self.write("[debug] type 'help' for commands")
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.input.setFocus()

    def stop(self):
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler.close()
            self._log_handler = None
        if self.window is not None:
            self.window.close()

    @pyqtSlot(str)
    def write(self, line):
        self._lines.append(line)
        if self.window is not None:
            # Independent widgets keep output from changing command text/focus.
            bar = self.window.output.verticalScrollBar()
            follow = bar.value() == bar.maximum()
            position = bar.value()
            self.window.output.appendPlainText(line)
            bar.setValue(bar.maximum() if follow else position)

    def _format_state_line(self, state_name):
        active = self.controller.behaviors.active
        return f"{state_name} | behavior {active.id if active else 'idle'}"

    def log_state_change(self, state_name):
        if state_name != self._last_logged_state_name:
            self._last_logged_state_name = state_name
            self.write(self._format_state_line(state_name))

    def print_current_state(self):
        node = self.controller.pet.current_animation_node()
        self.write(self._format_state_line(node.value if node is not None else 'unknown'))

    @pyqtSlot(str)
    def handle_command(self, line):
        parts = line.split()
        if not parts:
            return
        self.write(f'> {line}')
        cmd = parts[0].lower()
        if cmd == 'help':
            self._print_help()
        elif cmd == 'show':
            self.print_current_state()
        elif cmd == 'behaviors':
            self.write('[debug] behaviors: ' + ', '.join(sorted(self.controller.behaviors.registry)))
            for error in self.controller.behaviors.errors:
                self.write(f'[debug] behavior error: {error}')
        elif cmd == 'run':
            if len(parts) != 2:
                self.write('[debug] usage: run <behavior_id>')
            elif not self.controller.start_behavior(parts[1]):
                self.write('[debug] behavior unavailable or interaction is locked')
        elif cmd == 'hide':
            self.controller.debug_start_hide()
        elif cmd == 'schedule':
            for name, seconds in sorted(self.controller.behaviors.schedule_snapshot().items()):
                self.write(f'[debug] {name}: {seconds:.0f}s until due')
        else:
            self.write(f'[debug] unknown command: {cmd}')
            self._print_help()

    def _print_help(self):
        self.write('[debug] commands:')
        self.write('  hide              # force hide scenario')
        self.write('  show              # current state')
        self.write('  schedule          # time until scheduled behaviors')
        self.write('  behaviors         # list discovered scripts')
        self.write('  run <behavior_id> # start a registered behavior')
        self.write('  help')
