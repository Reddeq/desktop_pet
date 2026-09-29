import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class DebugConsole(QObject):
    command_received = pyqtSignal(str)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

        self._stop_event = threading.Event()
        self._thread = None

        self._last_logged_state_name = None

        self.command_received.connect(self.handle_command)

    def start(self):
        """
        Стартуем консоль только если есть живой stdin/tty.
        Это удобно для dev-запуска из терминала.
        """
        if sys.stdin is None or sys.stdin.closed:
            return

        try:
            interactive = sys.stdin.isatty()
        except Exception:
            interactive = False

        if not interactive:
            return

        print("[debug] console commands enabled")
        print("[debug] type 'help' for commands")

        self._thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _reader_loop(self):
        while not self._stop_event.is_set():
            try:
                line = input()
            except EOFError:
                break
            except Exception:
                break

            if line is None:
                continue

            line = line.strip()
            if not line:
                continue

            self.command_received.emit(line)

    # -------------------------
    # Formatting / logging
    # -------------------------

    def _format_state_line(self, state_name: str) -> str:
        needs = self.controller.needs.values
        return (
            f"{state_name} | "
            f"satiety {needs.satiety:.0f} | "
            f"energy {needs.energy:.0f} | "
            f"mood {needs.mood:.0f} | "
            f"bladder {needs.bladder:.0f}"
        )

    def log_state_change(self, state_name: str):
        """
        Печатает строку только если это действительно новое состояние.
        """
        if state_name == self._last_logged_state_name:
            return

        self._last_logged_state_name = state_name
        print(self._format_state_line(state_name))

    def print_current_state(self):
        node = self.controller.pet.current_animation_node()
        state_name = node.value if node is not None else "unknown"
        print(self._format_state_line(state_name))

    # -------------------------
    # Commands
    # -------------------------

    @pyqtSlot(str)
    def handle_command(self, line: str):
        parts = line.split()
        if not parts:
            return

        cmd = parts[0].strip().lower()

        if cmd == "help":
            self._print_help()
            return

        if cmd == "show":
            self.print_current_state()
            return

        if cmd == "behaviors":
            print("[debug] behaviors: " + ", ".join(sorted(self.controller.behaviors.registry)))
            for error in self.controller.behaviors.errors:
                print(f"[debug] behavior error: {error}")
            return

        if cmd == "run":
            if len(parts) != 2:
                print("[debug] usage: run <behavior_id>")
            elif not self.controller.start_behavior(parts[1]):
                print("[debug] behavior unavailable or interaction is locked")
            return

        if cmd in {"hide", "hiding"}:
            self.controller.debug_start_hiding()
            return

        if cmd in {"satiety", "energy", "mood", "bladder", "toilet"}:
            if len(parts) != 2:
                print(f"[debug] usage: {cmd} <0..100>")
                return

            try:
                value = float(parts[1])
            except ValueError:
                print(f"[debug] invalid value: {parts[1]}")
                return

            ok = self.controller.set_need_value(cmd, value)
            if not ok:
                print(f"[debug] invalid need or non-finite value: {cmd}")
                return

            self.print_current_state()
            return

        print(f"[debug] unknown command: {cmd}")
        self._print_help()

    def _print_help(self):
        print("[debug] commands:")
        print("  satiety <0..100>")
        print("  energy <0..100>")
        print("  mood <0..100>")
        print("  bladder <0..100>")
        print("  toilet <0..100>   # alias for bladder")
        print("  hide              # force hiding scenario")
        print("  hiding            # alias for hide")
        print("  show")
        print("  behaviors         # list automatically discovered scripts")
        print("  run <behavior_id> # start any registered behavior")
        print("  help")
