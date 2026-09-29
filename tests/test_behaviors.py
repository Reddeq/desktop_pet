"""Headless regression tests using real Qt timers and the real animator."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QPointF, QRect, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from animation_node import AnimationNode as N
from animation_player import AnimationPlayer
from behavior_runtime import Scenario
from pet_animator import PetAnimator
from pet_controller import PetController
from pet_needs import PetNeeds
from pet_state import PetState

APP = QApplication.instance() or QApplication([])


class FakePlayer:
    facing_right = True

    def set_animation(self, name, loop, force=False):
        self.current_animation = name
        return True


class FakePet:
    def __init__(self, width=100):
        self._x, self._y = 400, 500
        self._width = width
        self.ground_y = 500
        self.visible = True
        self.anchor = None
        self.current_state = PetState.IDLE
        self.animation_player = FakePlayer()
        self.animator = PetAnimator(self, self.animation_player)
        self.animator.set_initial_node(N.SITTING_IDLE)

    def x(self): return self._x
    def y(self): return self._y
    def width(self): return self._width
    def height(self): return 100
    def isVisible(self): return self.visible
    def show(self): self.visible = True
    def hide(self): self.visible = False
    def move(self, x, y): self._x, self._y = x, y
    def get_current_screen_rect(self): return QRect(0, 0, 1000, 600)
    def set_horizontal_edge_anchor(self, edge): self.anchor = edge
    def set_facing_right(self, value): self.animation_player.facing_right = value
    def current_animation_node(self): return self.animator.current_node
    def play_node(self, node, **kw): self.animator.play_sequence_nodes([node], **kw)
    def play_sequence_nodes(self, nodes, **kw): self.animator.play_sequence_nodes(nodes, **kw)
    def force_set_animation_node(self, node, hold=True): self.animator.force_set_node(node, hold)
    def interrupt_animation(self, node, recovery_targets): self.animator.interrupt_with(node, recovery_targets)
    def resolve_animation_interrupt(self): self.animator.resolve_interrupt()

    def clamp_position(self, x, y):
        return max(0, min(x, 1000 - self.width())), max(0, min(y, 500))

    def clamp_position_for_drag(self, x, y, point):
        return self.clamp_position(x, y)


class BehaviorTests(unittest.TestCase):
    def setUp(self):
        self.pet = FakePet()
        self.controller = PetController(self.pet, plugin_dirs=[])
        self.manager = self.controller.behaviors

    def tearDown(self):
        self.controller.stop()
        self.pet.animator.clear()
        self.controller.deleteLater()
        APP.processEvents()

    def finish_animation(self, node):
        self.pet.animator.on_animation_finished(node.value)
        self.controller.on_animation_finished(node.value)

    def reach(self, target):
        for _ in range(30):
            if self.pet.current_animation_node() == target:
                return
            step = self.pet.animator.current_step
            self.assertIsNotNone(step)
            from animation_graph import NODE_META
            meta = NODE_META[step.node]
            self.assertFalse(meta.requires_motion)
            if meta.loop:
                self.pet.animator._on_bridge_timeout()
            else:
                self.finish_animation(step.node)
        self.fail(f"Could not reach {target}")

    def test_all_builtins_discovered(self):
        self.assertEqual(set(self.manager.registry), {
            "idle", "walk", "cleaning", "sleep", "meowing", "eating",
            "food_begging", "notifications", "hiding", "toilet", "zoomies", "menu_meowing",
        })
        self.assertFalse(self.manager.errors)

    def test_sleep_priority_precedes_random_hiding(self):
        self.controller.needs.values.energy = 10
        self.controller.ctx.hiding_trigger_chance = 1
        self.controller.behavior.tick()
        self.assertEqual(self.manager.active.id, "sleep")

    def test_menu_blocks_urgent_toilet(self):
        self.controller.start_menu_meowing()
        self.controller.needs.values.bladder = 0
        self.manager.needs_tick()
        self.assertEqual(self.manager.active.id, "menu_meowing")

    def test_menu_during_fall_preserves_interrupt(self):
        self.controller.start_falling()
        self.controller.start_menu_meowing()
        self.controller.finish_menu_meowing()
        self.assertTrue(self.controller.ctx.is_falling)
        self.assertTrue(self.pet.animator.is_interrupt_active)

    def test_release_without_drag_does_not_start_recovery(self):
        self.controller.on_mouse_release()
        self.assertFalse(self.controller.ctx.is_recovering)

    def test_missing_animation_disables_scenario_without_hanging(self):
        def load(name, **kwargs):
            return name != N.CLEANING.value
        with patch.object(self.pet.animation_player, "set_animation", side_effect=load):
            with self.assertLogs(level="ERROR"):
                self.assertFalse(self.manager.start("cleaning"))
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_cleaning)
        self.assertEqual(self.pet.current_animation_node(), N.SITTING_IDLE)
        self.assertIn("cleaning", self.manager.disabled)

    def test_missing_run_clip_does_not_leave_orphan_motion(self):
        self.pet.animator.force_set_node(N.RUNNING)
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "running"):
            with self.assertLogs(level="ERROR"):
                self.assertFalse(self.manager.start("zoomies"))
        self.assertFalse(self.controller.ctx.is_walking)
        self.assertIsNone(self.manager.active)

    def test_high_mood_startled_swat_keeps_non_sticky_user_behavior(self):
        self.controller.needs.values.mood = 100
        ai = self.controller.cursor_ai
        ai._activate_swat_after_startled()
        self.assertTrue(ai._limited_startled_swat_active)
        self.assertTrue(self.controller.ctx.is_swatting_cursor)
        self.assertFalse(ai.cursor_resist_timer.isActive())
        ai.finish_cursor_swat_due_to_timeout()
        self.assertFalse(self.controller.ctx.is_swatting_cursor)

    def test_single_file_plugin_is_selected_and_receives_events(self):
        script = '''from behavior_runtime import Scenario
class Behavior(Scenario):
    id = "new_script"
    @classmethod
    def weight(cls, controller): return 100
    def on_start(self): self.events = ["start"]
    def on_tick(self): self.events.append("tick")
    def on_needs(self): self.events.append("needs")
    def on_animation_finished(self, node): self.events.append(node.value)
'''
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "new_script.py").write_text(script)
            other = PetController(self.pet, plugin_dirs=[directory])
            try:
                with patch("behavior_runtime.random.random", return_value=1), patch(
                    "behavior_runtime.random.choices", return_value=[other.behaviors.registry["new_script"]]
                ):
                    other.behavior.tick()
                active = other.behaviors.active
                self.assertEqual(active.id, "new_script")
                other.process_walk_step()
                other._on_needs_tick()
                other.on_animation_finished(N.YAWNING.value)
                self.assertEqual(active.events, ["start", "tick", "needs", "yawning"])
                self.assertTrue(other.is_busy())
                self.assertTrue(other.behaviors.blocks_cursor)
            finally:
                other.stop()
                other.deleteLater()

    def test_bad_and_duplicate_plugins_do_not_disable_valid_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "bad.py").write_text("broken syntax !")
            Path(directory, "duplicate.py").write_text(
                'from behavior_runtime import Scenario\nclass Behavior(Scenario):\n    id = "sleep"\n')
            with self.assertLogs("behavior_runtime", level="ERROR"):
                other = PetController(self.pet, plugin_dirs=[directory])
            try:
                self.assertEqual(len(other.behaviors.errors), 2)
                self.assertTrue(other.start_behavior("sleep"))
            finally:
                other.stop()
                other.deleteLater()

    def test_canceled_timer_cannot_interrupt_new_behavior(self):
        self.manager.start("cleaning")
        self.reach(N.CLEANING)
        self.controller.process_walk_step()
        old = self.manager.active
        timer = next(iter(old._timers))
        self.manager.start("sleep")
        self.assertFalse(timer.isActive())
        timer.timeout.emit()  # A queued callback from the previous run is harmless.
        self.assertEqual(self.manager.active.id, "sleep")
        self.assertFalse(self.controller.ctx.is_cleaning)

    def test_timer_starts_only_after_transition(self):
        self.pet.animator.force_set_node(N.SLEEPING)
        self.manager.start("cleaning")
        self.controller.process_walk_step()
        self.assertFalse(self.manager.active._timers)
        self.reach(N.CLEANING)
        self.controller.process_walk_step()
        self.assertEqual(len(self.manager.active._timers), 1)

    def test_real_timer_finishes_and_cancels_its_peers(self):
        class Timed(Scenario):
            id = "timed"
            def on_start(self):
                self.later(1, self.finish)
                self.later(5000, lambda: self.pet.hide())
        self.manager.registry[Timed.id] = Timed
        self.manager.start("timed")
        QTest.qWait(30)
        self.assertIsNone(self.manager.active)
        self.assertTrue(self.pet.visible)

    def test_runtime_failure_cleans_flags_and_disables_script(self):
        class Broken(Scenario):
            id = "broken"
            flags = ("is_cleaning",)
            def on_start(self):
                self.later(1000, self.finish)
                raise RuntimeError("test failure")
        self.manager.registry[Broken.id] = Broken
        with self.assertLogs("behavior_runtime", level="ERROR"):
            self.assertFalse(self.manager.start("broken"))
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_cleaning)
        self.assertFalse(self.manager.start("broken"))

    def test_meowing_and_pending_startle_block_autonomy(self):
        self.manager.start("meowing")
        self.assertTrue(self.controller.is_busy())
        self.controller.behavior.tick()
        self.assertEqual(self.manager.active.id, "meowing")
        self.finish_animation(N.MEOWING)
        self.assertIsNone(self.manager.active)
        self.controller.cursor_ai._rear_startle_pending_swat = True
        self.assertTrue(self.controller.is_busy())

    def test_cursor_does_not_interrupt_unknown_behavior(self):
        class Custom(Scenario):
            id = "custom"
        self.manager.registry[Custom.id] = Custom
        self.manager.start("custom")
        ai = self.controller.cursor_ai
        with patch.object(ai, "_update_cursor_motion_state", return_value=self.pet_point()), patch.object(
            ai, "start_rear_startled_swat"
        ) as startle:
            ai.check_cursor_proximity()
            startle.assert_not_called()
        self.assertFalse(ai.process_chase_step())
        self.assertEqual(self.manager.active.id, "custom")

    def pet_point(self):
        return QPointF(self.pet.x(), self.pet.y()).toPoint()

    def test_drag_cancels_scenario_and_recovery_restores_state(self):
        self.manager.start("sleep")
        self.controller.on_mouse_press(QPointF(400, 500))
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_sleeping)
        self.assertFalse(self.controller.start_behavior("cleaning"))
        self.controller.on_mouse_release()
        self.assertEqual(self.pet.current_state, PetState.FALLING_RECOVERY)
        self.finish_animation(N.FALLING_RECOVERY)
        self.assertEqual(self.pet.current_state, PetState.IDLE)
        self.assertFalse(self.controller.ctx.is_recovering)

    def test_menu_preserves_hiding_and_close_does_not_cancel_it(self):
        self.manager.start("hiding")
        active = self.manager.active
        self.controller.start_menu_meowing()
        self.assertIs(self.manager.active, active)
        self.assertTrue(self.controller.ctx.is_menu_open)
        self.controller.finish_menu_meowing()
        self.assertIs(self.manager.active, active)

    def test_menu_replays_meow_and_releases_on_close(self):
        self.controller.start_menu_meowing()
        self.finish_animation(N.MEOWING)
        self.assertEqual(self.pet.current_animation_node(), N.MEOWING)
        self.assertIsNotNone(self.pet.animator.current_step)
        self.controller.finish_menu_meowing()
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_meowing)

    def test_hiding_empty_bladder_falls_before_toilet(self):
        self.manager.start("hiding")
        self.controller.needs.values.bladder = 0
        self.manager.needs_tick()
        self.assertTrue(self.controller.ctx.is_falling)
        self.assertIsNone(self.manager.active)
        self.assertTrue(self.pet.visible)

    def test_toilet_waits_for_its_timer_and_digging_transition(self):
        self.manager.start("toilet")
        self.reach(N.RUNNING)
        self.controller.motion.stop_horizontal_motion()
        self.controller.process_walk_step()
        self.reach(N.POOPING)
        self.controller.process_walk_step()
        scenario = self.manager.active
        self.finish_animation(N.POOPING)
        self.assertEqual(self.pet.current_animation_node(), N.POOPING)
        self.assertEqual(scenario.phase, "pooping")
        scenario._dig()
        self.assertEqual(self.controller.needs.values.bladder, 100)
        self.reach(N.DIGGING)
        self.controller.process_walk_step()
        self.assertEqual(scenario.phase, "digging")
        scenario._zoomies()
        self.assertEqual(self.manager.active.id, "zoomies")
        self.assertFalse(self.controller.ctx.is_pooping)

    def test_zero_distance_zoomies_on_small_screen(self):
        self.pet._width = 1000
        self.pet._x = 0
        self.manager.start("zoomies")
        self.reach(N.RUNNING)
        self.controller.process_walk_step()
        self.assertEqual(self.manager.active.phase, "waiting")
        self.assertFalse(self.controller.ctx.is_walking)

    def test_eating_completes_before_urgent_toilet(self):
        self.controller.needs.values.satiety = 0
        self.controller.needs.values.bladder = 0
        self.assertTrue(self.controller.try_feed())
        self.manager.needs_tick()
        self.assertEqual(self.manager.active.id, "eating")
        self.reach(N.EATING)
        self.finish_animation(N.EATING)
        self.manager.needs_tick()
        self.assertEqual(self.manager.active.id, "toilet")

    def test_stop_cancels_all_owned_timers(self):
        self.controller.start()
        self.manager.start("zoomies")
        self.controller.stop()
        self.assertIsNone(self.manager.active)
        self.assertFalse(any(t.isActive() for t in self.controller.findChildren(QTimer)))


class AnimatorTests(unittest.TestCase):
    def setUp(self):
        self.pet = FakePet()
        self.animator = self.pet.animator

    def tearDown(self):
        self.animator.clear()

    def test_same_motion_node_at_head_is_not_skipped(self):
        self.animator.force_set_node(N.RUNNING)
        self.animator.play_sequence_nodes([N.RUNNING, N.STANDING_IDLE], force_restart=True)
        self.assertEqual(self.animator.current_node, N.RUNNING)
        self.animator.notify_motion_complete()
        self.assertEqual(self.animator.current_node, N.STANDING_IDLE)

    def test_initial_bridge_progresses(self):
        self.animator.current_node = None
        self.animator.current_step = None
        self.animator.play_sequence_nodes([N.SITTING_IDLE, N.MEOWING])
        self.assertTrue(self.animator.bridge_timer.isActive())
        self.animator._on_bridge_timeout()
        self.assertEqual(self.animator.current_node, N.MEOWING)

    def test_append_uses_queue_tail(self):
        self.animator.play_sequence_nodes([N.MEOWING, N.SLEEPING], force_restart=True)
        self.animator.play_sequence_nodes([N.CLEANING], replace=False)
        nodes = [step.node for step in self.animator.expanded_queue]
        sleep_index = nodes.index(N.SLEEPING)
        self.assertEqual(nodes[sleep_index + 1], N.SITTING_UP)
        self.assertFalse(self.animator.expanded_queue[sleep_index].hold)

    def test_repeated_one_shot_keeps_new_step(self):
        self.animator.play_sequence_nodes([N.MEOWING, N.MEOWING], force_restart=True)
        self.animator.on_animation_finished(N.MEOWING.value)
        self.assertIsNotNone(self.animator.current_step)

    def test_clear_and_force_set_release_interrupt(self):
        self.animator.interrupt_with(N.FALLING)
        self.animator.clear()
        self.assertFalse(self.animator.is_interrupt_active)
        self.animator.interrupt_with(N.FALLING)
        self.animator.force_set_node(N.SITTING_IDLE)
        self.assertFalse(self.animator.is_interrupt_active)


class NeedsAndPlayerTests(unittest.TestCase):
    def test_sleep_state_is_only_fallback(self):
        needs = PetNeeds()
        needs.values.energy = 50
        needs.tick(PetState.SLEEP, N.LAYING_DOWN)
        self.assertLess(needs.values.energy, 50)
        needs.tick(PetState.SLEEP, None)
        self.assertGreater(needs.values.energy, 50)

    def test_non_finite_need_rejected(self):
        needs = PetNeeds()
        for value in [float("nan"), float("inf"), "bad", None]:
            self.assertFalse(needs.set_need("energy", value))
        self.assertEqual(needs.values.energy, 100)

    def test_turn_does_not_restart_one_shot(self):
        player = AnimationPlayer("unused")
        player.timer.stop()
        frames = [QPixmap(1, 1) for _ in range(3)]
        with patch.object(player, "_load_frames", return_value=frames):
            player.set_animation("eating", loop=False)
            player._next_frame()
            player.set_facing_right(False)
            self.assertEqual(player.current_frame_index, 1)
            player._next_frame()
            player._next_frame()
            self.assertTrue(player._finished_emitted)
            player.set_facing_right(True)
            self.assertTrue(player._finished_emitted)
        player.deleteLater()


if __name__ == "__main__":
    unittest.main()
