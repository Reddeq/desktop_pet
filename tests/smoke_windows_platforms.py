"""Real Windows API integration using only disposable, test-owned windows.

Run on an interactive Windows desktop. Does not move the cursor or activate
user applications. The fixture is a separate process so own-window exclusion
is tested rather than bypassed.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


def fixture():
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication, QWidget
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = QWidget()
    window.setWindowTitle('Pixler disposable platform test')
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    screen = app.primaryScreen().availableGeometry()
    window.setGeometry(screen.left() + 400, screen.top() + 650, 800, 180)
    window.show()
    occluder = QWidget()
    occluder.setWindowTitle('Pixler disposable occluder')
    occluder.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    occluder.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    commands = queue.Queue()
    def read():
        for line in sys.stdin:
            commands.put(json.loads(line))
        commands.put({'op': 'quit'})
    threading.Thread(target=read, daemon=True).start()
    def reply():
        print(json.dumps({'hwnd': int(window.winId())}), flush=True)
    def execute():
        while not commands.empty():
            command = commands.get()
            operation = command['op']
            if operation == 'move':
                window.move(window.x() + command['dx'], window.y() + command['dy'])
            elif operation == 'resize':
                window.resize(command['width'], 180)
            elif operation == 'screen':
                target = app.screens()[command['index']].availableGeometry()
                window.move(target.left() + 400, target.top() + 650)
            elif operation == 'occlude':
                occluder.setGeometry(window.x() - 150, window.y() - 100, window.width() + 300, 200)
                occluder.show()
            elif operation == 'unocclude':
                occluder.hide()
            elif operation == 'minimize':
                window.showMinimized()
            elif operation == 'restore':
                window.showNormal()
            elif operation == 'close':
                window.close()
            elif operation == 'quit':
                app.quit()
                return
            QTimer.singleShot(60, reply)
    timer = QTimer()
    timer.timeout.connect(execute)
    timer.start(20)
    QTimer.singleShot(200, reply)
    app.exec()


def main():
    from unittest.mock import patch
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from app import FrameAnimatedPet
    from windows_tracker import WindowsTracker
    app = QApplication([])
    tracker = WindowsTracker()
    child = None
    pet = None
    try:
        tracker.start()
        windows, _ = tracker.scan()
        assert tracker.hooks, tracker.error
        assert tracker.monitor_rects(), 'No native monitors'
        print(f'Native discovery: {len(windows)} visible windows; {len(tracker.hooks)} hooks installed')
        child = subprocess.Popen([sys.executable, __file__, '--fixture'], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        replies = queue.Queue()
        def read_replies():
            for line in child.stdout:
                replies.put(json.loads(line))
        threading.Thread(target=read_replies, daemon=True).start()
        hwnd = replies.get(timeout=10)['hwnd']
        def command(operation, **values):
            child.stdin.write(json.dumps({'op': operation, **values}) + '\n')
            child.stdin.flush()
            replies.get(timeout=10)
            QTest.qWait(80)
        pet = FrameAnimatedPet()
        pet.controller.stop()
        pet.debug_console.stop()
        pet.hide()
        QTest.qWait(150)  # Drain native startup move/show messages before attachment.
        surfaces = pet.controller.surfaces
        surfaces.tracker = tracker
        surfaces.set_enabled(True)
        def attach():
            surfaces.refresh()
            platform = next(p for p in surfaces.snapshot.platforms if p.window == hwnd)
            pet.move(round(platform.left + 50), round(platform.y - pet.height()))
            surfaces.attach(platform)
            return platform
        platform = attach()
        own = int(pet.winId())
        assert all(w.handle != own for w in tracker.scan()[0])
        old = (pet.x(), pet.y())
        node = pet.current_animation_node()
        command('move', dx=45, dy=-20)
        surfaces._follow()
        assert (pet.x(), pet.y()) == (old[0] + 45, old[1] - 20), (old, (pet.x(), pet.y()),
            platform, tracker.window(hwnd), pet.controller.ctx.is_fall)
        assert pet.current_animation_node() == node
        print('Native window movement: attachment and animation preserved')
        assert tracker.dirty.is_set(), 'Native window events did not mark the cache dirty'
        if len(app.screens()) > 1:
            old_monitor = surfaces.current.monitor
            command('screen', index=1)
            surfaces._follow()
            assert not pet.controller.ctx.is_fall
            assert surfaces.current.monitor != old_monitor
            surfaces.refresh()
            assert surfaces.on_window
            print('Native move between monitors: attachment follows to the destination screen')
        command('resize', width=100)
        surfaces._follow()
        assert pet.controller.ctx.is_fall
        command('resize', width=800)
        pet.controller._reset_motion_flags()
        attach()
        command('minimize')
        surfaces._follow()
        assert pet.controller.ctx.is_fall
        command('restore')
        pet.controller._reset_motion_flags()
        attach()
        command('occlude')
        surfaces.refresh()
        assert pet.controller.ctx.is_fall
        command('unocclude')
        pet.controller._reset_motion_flags()
        attach()
        command('close')
        surfaces._follow()
        assert pet.controller.ctx.is_fall
        print('Native resize/minimize/occlusion/close: missing support starts gravity')
        assert len(surfaces.monitors) == len(app.screens()), 'Native/Qt monitor mappings differ'
        print(f'Native/Qt coordinates: {len(surfaces.monitors)} monitors mapped; own windows excluded')
    finally:
        tracker.close()
        if pet is not None:
            pet.controller.stop()
            pet.close()
        if child is not None:
            if child.poll() is None:
                child.stdin.write('{"op":"quit"}\n')
                child.stdin.flush()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
        assert not tracker.hooks
        print('Native hooks and disposable fixture released')


if __name__ == '__main__':
    if '--fixture' in sys.argv:
        fixture()
    else:
        main()
