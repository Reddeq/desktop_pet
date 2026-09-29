"""Scenario integration checks without a GUI/display."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


class Signal:
    def connect(self, callback):
        self.callback = callback


class Timer:
    def __init__(self, parent=None):
        self.timeout = Signal()
        self.active = False

    def setSingleShot(self, value):
        pass

    def start(self, interval):
        self.active = True

    def stop(self):
        self.active = False


qt = types.ModuleType('PyQt6')
core = types.ModuleType('PyQt6.QtCore')
core.QTimer = Timer
core.QObject = object
core.QPoint = object
gui = types.ModuleType('PyQt6.QtGui')
gui.QCursor = SimpleNamespace(pos=lambda: None)
qt.QtCore = core
qt.QtGui = gui
sys.modules.setdefault('PyQt6', qt)
sys.modules.setdefault('PyQt6.QtCore', core)
sys.modules.setdefault('PyQt6.QtGui', gui)

import pet_scenarios
from pet_behavior import PetBehavior
from pet_context import PetContext
from pet_state import PetState


class Pet:
    def __init__(self):
        self.current_state = PetState.IDLE
        self.animation_player = SimpleNamespace(has_frames=lambda: True)

    def set_state(self, value):
        self.current_state = value


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.pet = Pet()
        self.ctx = PetContext()
        self.controller = SimpleNamespace(
            pet=self.pet, ctx=self.ctx, motion=SimpleNamespace(start_walk=lambda *a: None),
            needs=SimpleNamespace(is_sleepy=lambda threshold: False,
                                  values=SimpleNamespace(energy=50)),
            _reset_motion_flags=lambda: None,
        )
        self.behavior = PetBehavior(self.controller)
        self.controller.behavior = self.behavior

    def test_discovery_and_priority(self):
        self.assertEqual(set(self.behavior.by_name),
                         {'idle', 'walk', 'cleaning', 'sleep', 'notifications', 'cursor', 'drag'})
        self.controller.needs.is_sleepy = lambda threshold: True
        self.behavior.tick()
        self.assertEqual(self.pet.current_state, PetState.SLEEP)
        self.assertTrue(self.ctx.is_sleeping)
        self.controller.needs.values.energy = 100
        self.behavior.on_needs_tick()
        self.assertEqual(self.pet.current_state, PetState.IDLE)

    def test_cancelled_cleaning_does_not_finish_later(self):
        cleaning = self.behavior.by_name['cleaning']
        cleaning.start()
        self.assertTrue(cleaning.timer.active)
        self.behavior.cancel()
        self.assertFalse(cleaning.timer.active)
        self.assertFalse(self.ctx.is_cleaning)

    def test_one_file_scenario_discovered(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'stretch.py').write_text(
                'from pet_scenarios import BehaviorScenario\n'
                'class Stretch(BehaviorScenario):\n'
                '    name = "stretch"\n    weight = 0.05\n'
                '    def start(self): self.pet.set_state("stretch")\n'
            )
            pet_scenarios.__path__.append(folder)
            try:
                behavior = PetBehavior(self.controller)
                self.assertIn('stretch', behavior.by_name)
                behavior.by_name['stretch'].start()
                self.assertEqual(self.pet.current_state, 'stretch')
            finally:
                pet_scenarios.__path__.remove(folder)
                sys.modules.pop('pet_scenarios.stretch', None)


if __name__ == '__main__':
    unittest.main()
