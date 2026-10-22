"""Synthetic platforms with the actual sprite clock, movement and settings UI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from PyQt6.QtCore import QElapsedTimer, QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from animation_node import AnimationNode as N
from app import FrameAnimatedPet
from pet_settings import PetSettings
from surface_controller import qt_rect, screen_id
from surfaces import Monitor, Rect, Window


def wait_until(predicate, label, timeout=6000):
    elapsed = QElapsedTimer()
    elapsed.start()
    while not predicate() and elapsed.elapsed() < timeout:
        QTest.qWait(10)
    assert predicate(), f'Timed out: {label}'


class Tracker:
    def __init__(self, window):
        self.windows = [window]
        self.dirty = threading.Event()
    def start(self): pass
    def close(self): pass
    def scan(self): return self.windows, None
    def window(self, handle): return next((w for w in self.windows if w.handle == handle), None)


def main():
    app = QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        settings = PetSettings(QSettings(str(Path(directory) / 'preferences.ini'), QSettings.Format.IniFormat))
        with patch('app.PetSettings', return_value=settings):
            pet = FrameAnimatedPet()
        pet.controller.stop()
        pet.debug_console.stop()
        controller = pet.controller
        surfaces = controller.surfaces
        screen = pet.get_active_clamp_screen()
        work = qt_rect(screen.availableGeometry())
        monitor = Monitor(screen_id(screen), qt_rect(screen.geometry()), qt_rect(screen.geometry()), work)
        window = Window(12345, Rect(work.left + 450, work.bottom - 250, work.right, work.bottom - 50))
        tracker = Tracker(window)
        surfaces.tracker = tracker
        surfaces._monitors = lambda: (monitor,)
        try:
            assert not settings.walk_on_windows
            button = pet.context_menu.menu.windows_button
            assert not button.isChecked()
            button.click()
            assert settings.walk_on_windows and surfaces.enabled
            source = surfaces.desktop()
            target = next(p for p in surfaces.snapshot.platforms if p.window)
            plan = surfaces.navigator.plan(source, target, pet.width(), pet.height(),
                                           [window.rect], work)
            assert plan is not None, 'Fixture has no clear route'
            pet.move(round(plan.launch_x), round(source.y - pet.height()))
            pet.force_set_animation_node(N.STAND_IDLE)
            controller.walk_timer.start()
            controller.gravity_timer.start()
            surfaces.travel.begin(plan)
            wait_until(lambda: surfaces.travel.phase == 'jump', 'approach and wind-up')
            assert pet.current_animation_node() == N.JUMP
            assert len(pet.animation_player.frames) == 11
            wait_until(lambda: surfaces.on_window and not surfaces.travel.active, 'land on window')
            assert pet.y() + pet.height() == round(target.y)
            assert controller.start_behavior('walk')
            wait_until(lambda: controller.behaviors.active is None, 'ordinary walk on window')
            assert surfaces.current.fits(pet.x(), pet.width())
            assert controller.start_behavior('clean')
            wait_until(lambda: pet.current_animation_node() == N.CLEAN, 'groom on window')
            scenario = controller.behaviors.active
            old_x, old_y = pet.x(), pet.y()
            tracker.windows = [Window(12345, Rect(window.rect.left - 20, window.rect.top - 15,
                                                 window.rect.right - 20, window.rect.bottom - 15))]
            tracker.dirty.set()
            QTest.qWait(150)
            assert controller.behaviors.active is scenario
            assert (pet.x(), pet.y()) == (old_x - 20, old_y - 15)
            button.click()
            assert not settings.walk_on_windows and not surfaces.enabled
            assert controller.ctx.is_fall
            wait_until(lambda: controller.ctx.is_recover, 'safe return after disabling')
            assert pet.y() + pet.height() == round(work.bottom)
            wait_until(lambda: not controller.ctx.is_recover, 'landing recovery')
            button.click()
            assert controller.start_behavior('window_drop')
            entry = controller.behaviors.active
            partial_heights = []
            def record_entry():
                if entry.phase == 'fall' and controller.ctx.is_fall:
                    partial_heights.append(pet.geometry().intersected(screen.geometry()).height())
            controller.walk_timer.timeout.connect(record_entry)
            wait_until(lambda: entry.phase == 'fall', 'run offscreen then drop from top')
            wait_until(lambda: controller.behaviors.active is None, 'top entry landing and recovery')
            controller.walk_timer.timeout.disconnect(record_entry)
            assert any(0 < height < pet.height() for height in partial_heights)
            assert surfaces.on_window and pet.label.clip_rect is None
            with patch('surface_controller.random.random', return_value=0):
                assert controller.start_behavior('hide')
            assert surfaces.travel.after_behavior == 'hide'
            wait_until(lambda: controller.behaviors.active is not None
                       and controller.behaviors.active.id == 'hide', 'descend before deferred hide')
            assert not surfaces.elevated
            assert pet.y() + pet.height() == round(work.bottom)
            controller.start_idle()
            tracker.windows = [Window(12345, Rect(window.rect.left - 20,
                                                 work.top + pet.height(),
                                                 window.rect.right - 20, work.bottom - 50))]
            surfaces.refresh()
            high = next(p for p in surfaces.snapshot.platforms if p.window)
            pet.move(round(high.left + 6), round(high.y - pet.height()))
            surfaces.attach(high)
            pet.force_set_animation_node(N.STAND_IDLE)
            with patch('surface_controller.random.random', return_value=0):
                assert controller.start_behavior('hide')
            wait_until(lambda: controller.behaviors.active is not None
                       and controller.behaviors.active.id == 'hide', 'descent with zero upward headroom')
            assert pet.y() + pet.height() == round(work.bottom)
            controller.start_idle()
            print('Qt platforms: movement, top entry, deferred hide and descent from a window at the screen ceiling OK')
        finally:
            controller.stop()
            pet.close()


if __name__ == '__main__':
    main()
