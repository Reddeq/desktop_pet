"""Headless regression tests using real Qt timers and the real animator."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from PyQt6.QtCore import QPoint, QPointF, QRect, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from animation_node import AnimationNode as N
from animation_player import AnimationPlayer
from behavior_runtime import Scenario
from pet_animator import PetAnimator
from pet_controller import PetController
from pet_state import PetState

APP = QApplication.instance() or QApplication([])


class FakePlayer:
    facing_right = True

    def set_animation(self, name, loop, force=False):
        self.current_animation = name
        self.current_loop = loop
        return True


class FakePet:
    def __init__(self, width=100):
        self._x, self._y = 400, 500
        self._width = width
        self.ground_y = 500
        self.visible = True
        self.anchor = None
        self.screen_clip = None
        self.current_state = PetState.IDLE
        self.animation_player = FakePlayer()
        self.animator = PetAnimator(self, self.animation_player)
        self.animator.set_initial_node(N.SIT_IDLE)

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
    def set_screen_clip(self, rect): self.screen_clip = rect
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

    def finish_eating(self):
        self.controller.process_walk_step()
        scenario = self.manager.active
        timer = next(iter(scenario._timers))
        self.assertEqual(timer.interval(), 5000)
        timer.stop()
        timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.EAT.value)

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

    def test_missing_recovery_releases_interaction_lock(self):
        self.controller.start_fall()
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "recover"):
            with self.assertLogs(level="ERROR"):
                self.controller.motion._land()
        self.assertFalse(self.controller.interaction_locked)
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)
        self.assertTrue(self.controller.start_behavior("clean"))

    def test_missing_fall_still_lands_and_recovers(self):
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "fall"):
            with self.assertLogs(level="ERROR"):
                self.controller.start_fall()
        self.controller.motion._land()
        self.reach(N.RECOVER)
        self.finish_animation(N.RECOVER)
        self.assertFalse(self.controller.interaction_locked)

    def test_missing_swat_does_not_restart_canceled_timers(self):
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "swat"):
            self.pet.animator.force_set_node(N.STAND_IDLE)
            with self.assertLogs(level="ERROR"):
                self.controller.cursor_ai.start_cursor_swat()
        self.assertFalse(self.controller.cursor_ai.cursor_resist_timer.isActive())
        self.assertFalse(self.controller.ctx.is_swat_cursor)

    def test_hunt_waits_for_stand_up_without_restarting(self):
        ai = self.controller.cursor_ai
        with patch("pet_cursor_ai.QCursor.pos", return_value=QPoint(700, 550)):
            self.assertTrue(ai.start_cursor_hunt())
        step = self.pet.animator.current_step
        self.assertEqual(step.node, N.STAND_UP)
        with patch("pet_cursor_ai.QCursor.pos", return_value=self.pet_point()), patch.object(ai, "_can_swat_cursor_strict", return_value=False), patch.object(ai, "_cursor_is_reachable_in_y_strict", return_value=True):
            for _ in range(10):
                ai.process_chase_step()
        self.assertIs(self.pet.animator.current_step, step)
        self.assertEqual(self.pet.x(), 400)
        self.reach(N.SNEAK)

    def begin_sneak(self):
        self.pet.animator.force_set_node(N.STAND_IDLE)
        ai = self.controller.cursor_ai
        with patch("pet_cursor_ai.QCursor.pos", return_value=QPoint(700, 550)):
            self.assertTrue(ai.start_cursor_hunt())
        self.assertEqual(self.pet.current_animation_node(), N.START_SNEAK)
        self.reach(N.SNEAK)
        return ai

    def test_sneak_movement_does_not_restart_the_loop(self):
        ai = self.begin_sneak()
        step = self.pet.animator.current_step
        x = self.pet.x()
        with patch("pet_cursor_ai.QCursor.pos", return_value=QPointF(900, 550).toPoint()), patch.object(ai, "_can_swat_cursor_strict", return_value=False):
            for _ in range(10):
                self.assertTrue(ai.process_chase_step())
        self.assertIs(self.pet.animator.current_step, step)
        self.assertGreater(self.pet.x(), x)

    def test_sneak_idle_exit_waits_for_loop_and_stand_up(self):
        ai = self.begin_sneak()
        ai.finish_cursor_hunt()
        x = self.pet.x()
        self.assertTrue(self.controller.is_busy())
        self.assertEqual(self.pet.current_animation_node(), N.SNEAK)
        self.assertTrue(ai.process_chase_step())
        self.assertEqual(self.pet.x(), x)
        self.controller.on_animation_loop_finished(N.SNEAK.value)
        self.assertEqual(self.pet.current_animation_node(), N.END_SNEAK)
        step = self.pet.animator.current_step
        ai.check_cursor_proximity()
        ai.process_chase_step()
        self.assertIs(self.pet.animator.current_step, step)
        self.assertTrue(self.controller.is_busy())
        self.finish_animation(N.END_SNEAK)
        self.assertFalse(self.controller.ctx.is_hunt_cursor)
        self.reach(N.SIT_IDLE)

    def test_sneak_reaching_cursor_delays_swat_until_exit(self):
        ai = self.begin_sneak()
        ai.start_wait_to_swat()
        self.assertFalse(self.controller.ctx.is_wait_to_swat)
        self.assertFalse(ai.swat_prepare_timer.isActive())
        self.controller.on_animation_loop_finished(N.SNEAK.value)
        self.assertEqual(self.pet.current_animation_node(), N.END_SNEAK)
        self.assertFalse(ai.swat_prepare_timer.isActive())
        self.finish_animation(N.END_SNEAK)
        self.assertTrue(self.controller.ctx.is_wait_to_swat)
        self.assertFalse(self.controller.ctx.is_hunt_cursor)
        self.assertEqual(self.pet.current_animation_node(), N.STAND_IDLE)
        self.assertTrue(ai.swat_prepare_timer.isActive())

    def test_drag_cancels_pending_sneak_exit(self):
        ai = self.begin_sneak()
        ai.start_wait_to_swat()
        self.controller.on_mouse_press(QPointF(self.pet.x(), self.pet.y()))
        self.controller.on_animation_loop_finished(N.SNEAK.value)
        self.controller.on_animation_finished(N.END_SNEAK.value)
        self.assertTrue(self.controller.ctx.is_drag)
        self.assertIsNone(ai._hunt_exit_target)
        self.assertFalse(ai.swat_prepare_timer.isActive())
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)

    def test_missing_sneak_exit_clears_hunt_lock(self):
        ai = self.begin_sneak()
        ai.finish_cursor_hunt()
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "end_sneak"):
            with self.assertLogs(level="ERROR"):
                self.controller.on_animation_loop_finished(N.SNEAK.value)
        self.assertFalse(self.controller.ctx.is_hunt_cursor)
        self.assertIsNone(ai._hunt_exit_target)
        self.assertFalse(self.controller.is_busy())
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)

    def test_queued_swat_prepare_does_not_cancel_new_scenario(self):
        self.manager.start("clean")
        active = self.manager.active
        self.controller.cursor_ai._finish_wait_and_start_swat()
        self.assertIs(self.manager.active, active)

    def test_large_finite_plugin_weights_do_not_overflow(self):
        with patch.object(self.manager, "_trigger", return_value=False), patch.object(self.manager, "_score", return_value=1e308):
            self.manager.logic_tick()
        self.assertFalse(self.manager.errors)

    def test_all_builtins_discovered(self):
        self.assertEqual(set(self.manager.registry), {
            "idle", "walk", "clean", "sleep", "meow", "eat", "enter",
            "beg_food", "food_beg", "inspect_notifications", "hide", "poop", "run", "menu_meow", "sharpen_claws", "sandbath", "window_drop",
        })
        self.assertFalse(self.manager.errors)

    def test_due_sleep_priority_precedes_due_hide(self):
        self.manager._next_due.update(sleep=0, hide=0)
        self.controller.behaviors.logic_tick()
        self.assertEqual(self.manager.active.id, "sleep")

    def test_scheduled_behavior_waits_for_deadline(self):
        self.manager._clock = lambda: 100
        self.manager._next_due = {"sleep": 101}
        with patch.object(self.manager, "_score", return_value=0):
            self.manager.logic_tick()
        self.assertIsNone(self.manager.active)
        self.manager._clock = lambda: 101
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "sleep")
        self.assertGreaterEqual(self.manager._next_due["sleep"], 701)
        self.assertLessEqual(self.manager._next_due["sleep"], 1001)

    def test_sandbath_waits_while_busy_rolls_for_timer_and_finishes_cycle(self):
        from animation_graph import NODE_META
        self.manager._clock = lambda: 100
        self.manager._next_due = {'sandbath': 0}
        self.manager.start('clean')
        clean = self.manager.active
        self.manager.logic_tick()
        self.assertIs(self.manager.active, clean)
        self.assertEqual(self.manager._next_due['sandbath'], 0)
        self.controller.start_idle()
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, 'sandbath')
        self.assertGreaterEqual(self.manager._next_due['sandbath'], 340)
        self.assertLessEqual(self.manager._next_due['sandbath'], 520)
        scenario = self.manager.active
        self.reach(N.START_SANDBATH)
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)
        self.reach(N.SANDBATH)
        self.assertTrue(NODE_META[N.SANDBATH].loop)
        self.controller.process_walk_step()
        timer = next(iter(scenario._timers))
        self.assertGreaterEqual(timer.interval(), 4000)
        self.assertLessEqual(timer.interval(), 7000)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(self.pet.current_animation_node(), N.SANDBATH)
        self.controller.on_animation_loop_finished(N.SANDBATH.value)
        self.assertIs(self.manager.active, scenario)
        self.assertEqual(self.pet.current_animation_node(), N.END_SANDBATH)
        self.finish_animation(N.END_SANDBATH)
        self.assertIsNone(self.manager.active)
        self.reach(N.SIT_IDLE)
        self.assertFalse(self.manager.errors)

    def test_sandbath_drag_cancels_and_late_completion_is_harmless(self):
        self.manager.start('sandbath')
        self.reach(N.SANDBATH)
        self.controller.process_walk_step()
        timer = next(iter(self.manager.active._timers))
        self.controller.on_mouse_press(QPointF(self.pet.x(), self.pet.y()))
        self.assertFalse(timer.isActive())
        timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.SANDBATH.value)
        self.controller.on_animation_finished(N.END_SANDBATH.value)
        self.assertIsNone(self.manager.active)
        self.assertTrue(self.controller.ctx.is_drag)
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)

    def test_sharpen_claws_full_sequence_at_either_edge_without_cursor_capture(self):
        for edge in ('left', 'right'):
            with self.subTest(edge=edge), patch('behaviors.sharpen_claws.random.choice', return_value=edge), patch(
                'pet_cursor_ai.QCursor.setPos'
            ) as move_cursor:
                self.manager.start('sharpen_claws')
                scenario = self.manager.active
                self.reach(N.RUN)
                for _ in range(250):
                    self.controller.process_walk_step()
                    if scenario.phase == 'start':
                        break
                self.assertEqual(scenario.phase, 'start')
                self.assertIsNotNone(self.pet.screen_clip)
                self.assertEqual(self.pet.animation_player.facing_right, edge == 'right')
                self.assertFalse(scenario._timers)
                self.reach(N.SHARPEN_CLAWS)
                self.controller.process_walk_step()
                self.assertEqual(scenario.phase, 'loop')
                timer = next(iter(scenario._timers))
                self.assertGreaterEqual(timer.interval(), 4000)
                self.assertLessEqual(timer.interval(), 8000)
                timer.stop()
                timer.timeout.emit()
                self.assertEqual(self.pet.current_animation_node(), N.SHARPEN_CLAWS)
                self.controller.on_animation_loop_finished(N.SHARPEN_CLAWS.value)
                self.assertEqual(self.pet.current_animation_node(), N.END_SHARPEN_CLAWS)
                self.finish_animation(N.END_SHARPEN_CLAWS)
                self.reach(N.RUN)
                for _ in range(100):
                    self.controller.process_walk_step()
                    if self.manager.active is None:
                        break
                self.assertIsNone(self.manager.active)
                self.assertIsNone(self.pet.screen_clip)
                self.assertFalse(self.controller.cursor_ai.cursor_resist_timer.isActive())
                move_cursor.assert_not_called()

    def test_cancel_sharpen_claws_cleans_edge_clip_and_late_timer(self):
        self.manager.start('sharpen_claws')
        scenario = self.manager.active
        self.reach(N.RUN)
        self.controller.motion.stop_horizontal_motion()
        self.controller.process_walk_step()
        self.reach(N.SHARPEN_CLAWS)
        self.controller.process_walk_step()
        timer = next(iter(scenario._timers))
        self.controller.on_mouse_press(QPointF(self.pet.x(), self.pet.y()))
        self.assertFalse(timer.isActive())
        self.assertIsNone(self.pet.screen_clip)
        timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.SHARPEN_CLAWS.value)
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)

    def test_due_poop_waits_for_hidden_scenario(self):
        scenario = self.begin_hide_peek()
        self.manager._next_due["poop"] = 0
        self.manager.logic_tick()
        self.assertIs(self.manager.active, scenario)
        self.assertEqual(scenario.phase, "start")
        self.assertGreater(self.manager._next_due["poop"], self.manager._clock())

    def test_sleep_duration_starts_after_transition_and_wakes(self):
        self.manager.start("sleep")
        scenario = self.manager.active
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)
        self.reach(N.SLEEP)
        self.controller.process_walk_step()
        timer = next(iter(scenario._timers))
        self.assertGreaterEqual(timer.interval(), 30_000)
        self.assertLessEqual(timer.interval(), 60_000)
        timer.stop()
        timer.timeout.emit()
        self.assertIs(self.manager.active, scenario)
        self.assertEqual(self.pet.current_animation_node(), N.SLEEP)
        self.controller.on_animation_loop_finished(N.SLEEP.value)
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_sleep)
        self.reach(N.SIT_IDLE)

    def test_feeding_postpones_request_and_repeated_click_does_not_restart(self):
        self.manager._clock = lambda: 100
        self.manager._next_due["beg_food"] = 0
        self.assertTrue(self.controller.try_feed())
        active = self.manager.active
        self.assertFalse(self.controller.try_feed())
        self.assertIs(self.manager.active, active)
        self.assertGreaterEqual(self.manager._next_due["beg_food"], 340)
        self.assertLessEqual(self.manager._next_due["beg_food"], 520)
        self.assertFalse(hasattr(self.controller, "needs"))

    def test_feeding_does_not_interrupt_sleep_or_hide(self):
        for behavior_id in ["sleep", "hide"]:
            self.manager.start(behavior_id)
            active = self.manager.active
            self.assertFalse(self.controller.try_feed())
            self.assertIs(self.manager.active, active)

    def test_overdue_scenarios_run_once_without_catching_up_missed_periods(self):
        self.manager._clock = lambda: 100_000
        self.manager._next_due = {"beg_food": 0}
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "beg_food")
        self.manager.active.finish()
        with patch.object(self.manager, "_score", return_value=0):
            self.manager.logic_tick()
        self.assertIsNone(self.manager.active)
        self.assertGreater(self.manager._next_due["beg_food"], 100_000)

    def test_timed_plugin_registers_and_invalid_interval_is_isolated(self):
        script = 'from behavior_runtime import Scenario\nclass Behavior(Scenario):\n    id = "timed_plugin"\n    interval_seconds = (2, 3)\n'
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "timed.py").write_text(script)
            Path(directory, "bad.py").write_text(script.replace('"timed_plugin"', '"bad_interval"').replace('(2, 3)', '(3, 0)'))
            with self.assertLogs("behavior_runtime", level="ERROR"):
                other = PetController(self.pet, plugin_dirs=[directory])
            try:
                self.assertIn("timed_plugin", other.behaviors.schedule_snapshot())
                self.assertNotIn("bad_interval", other.behaviors.registry)
                other.behaviors._next_due["timed_plugin"] = 0
                other.behaviors.logic_tick()
                self.assertEqual(other.behaviors.active.id, "timed_plugin")
            finally:
                other.stop()
                other.deleteLater()

    def test_distant_feed_cursor_suppresses_hunt_without_starting_food_requests(self):
        ai = self.controller.cursor_ai
        with patch.object(ai, "_feed_mode_active", return_value=True), patch.object(
            ai, "start_cursor_hunt"
        ) as hunt, patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(-1000, -1000)):
            for _ in range(3):
                ai.check_cursor_proximity()
            hunt.assert_not_called()
        self.assertIsNone(self.manager.active)

    def test_nearby_food_cursor_keeps_request_looping_without_timer_or_restart(self):
        ai = self.controller.cursor_ai
        with patch.object(ai, '_feed_mode_active', return_value=True), patch(
            'pet_cursor_ai.QCursor.pos', return_value=QPoint(450, 550)
        ):
            ai.check_cursor_proximity()
            scenario = self.manager.active
            self.assertEqual(scenario.id, 'food_beg')
            self.reach(N.SCRATCH_SCREEN)
            self.assertTrue(self.pet.animation_player.current_loop)
            self.manager._clock = lambda: 100_000
            for _ in range(10):
                ai.check_cursor_proximity()
                self.controller.process_walk_step()
                self.controller.on_animation_loop_finished(N.SCRATCH_SCREEN.value)
                self.manager.logic_tick()
                self.assertIs(self.manager.active, scenario)
            self.assertFalse(scenario._timers)
            self.assertFalse(self.controller.ctx.is_hunt_cursor)

    def test_food_beg_ends_when_mode_changes_cursor_leaves_or_cooldown_starts(self):
        ai = self.controller.cursor_ai
        for reason in ('mode', 'distance', 'cooldown'):
            with self.subTest(reason=reason), patch.object(
                ai, '_feed_mode_active', return_value=True
            ) as mode, patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(450, 550)) as cursor:
                self.controller.food_cooldown_until = 0
                ai.check_cursor_proximity()
                self.assertEqual(self.manager.active.id, 'food_beg')
                self.reach(N.SCRATCH_SCREEN)
                if reason == 'mode':
                    mode.return_value = False
                elif reason == 'distance':
                    cursor.return_value = QPoint(-1000, -1000)
                else:
                    self.controller.food_cooldown_until = self.manager._clock() + 60
                self.controller.process_walk_step()
                self.assertIsNone(self.manager.active)
                self.assertFalse(self.controller.ctx.is_scratch_for_food)
                self.reach(N.SIT_IDLE)

    def test_food_beg_obeys_food_cooldown_and_ignores_post_swat_caution(self):
        ai = self.controller.cursor_ai
        self.manager._clock = lambda: 100
        self.controller.food_cooldown_until = 160
        self.controller.ctx.is_post_swat_cautious = True
        with patch.object(ai, '_feed_mode_active', return_value=True), patch(
            'pet_cursor_ai.QCursor.pos', return_value=QPoint(450, 550)
        ):
            ai.check_cursor_proximity()
            self.assertIsNone(self.manager.active)
            self.manager._clock = lambda: 160
            ai.check_cursor_proximity()
            self.assertEqual(self.manager.active.id, 'food_beg')

    def test_feeding_replaces_food_beg_and_proximity_does_not_interrupt_eating(self):
        ai = self.controller.cursor_ai
        with patch.object(ai, '_feed_mode_active', return_value=True), patch(
            'pet_cursor_ai.QCursor.pos', return_value=QPoint(450, 550)
        ):
            ai.check_cursor_proximity()
            scenario = self.manager.active
            self.reach(N.SCRATCH_SCREEN)
            self.assertTrue(self.controller.try_feed())
            self.assertEqual(self.manager.active.id, 'eat')
            self.assertFalse(self.controller.ctx.is_scratch_for_food)
            scenario.on_tick()  # A stale tick cannot finish the replacement.
            ai.check_cursor_proximity()
            self.assertEqual(self.manager.active.id, 'eat')
            self.assertFalse(self.controller.try_feed())

    def test_food_cursor_does_not_interrupt_hidden_sleeping_or_physical_scenarios(self):
        ai = self.controller.cursor_ai
        with patch.object(ai, '_feed_mode_active', return_value=True), patch(
            'pet_cursor_ai.QCursor.pos', return_value=QPoint(450, 550)
        ):
            for behavior in ('sleep', 'hide', 'enter', 'clean'):
                self.manager.start(behavior)
                scenario = self.manager.active
                ai.check_cursor_proximity()
                self.assertIs(self.manager.active, scenario)
            self.controller.on_mouse_press(QPointF(450, 550))
            ai.check_cursor_proximity()
            self.assertTrue(self.controller.ctx.is_drag)
            self.assertIsNone(self.manager.active)

    def test_menu_defers_due_poop(self):
        self.controller.start_menu_meow()
        self.manager._next_due["poop"] = 0
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "menu_meow")

    def test_menu_during_fall_preserves_interrupt(self):
        self.controller.start_fall()
        self.controller.start_menu_meow()
        self.controller.finish_menu_meow()
        self.assertTrue(self.controller.ctx.is_fall)
        self.assertTrue(self.pet.animator.is_interrupt_active)

    def test_release_without_drag_does_not_start_recovery(self):
        self.controller.on_mouse_release()
        self.assertFalse(self.controller.ctx.is_recover)

    def test_missing_animation_disables_scenario_without_hanging(self):
        def load(name, **kwargs):
            return name != N.START_CLEAN.value
        with patch.object(self.pet.animation_player, "set_animation", side_effect=load):
            with self.assertLogs(level="ERROR"):
                self.assertFalse(self.manager.start("clean"))
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_clean)
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)
        self.assertIn("clean", self.manager.disabled)

    def test_missing_run_clip_does_not_leave_orphan_motion(self):
        self.pet.animator.force_set_node(N.RUN)
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "run"):
            with self.assertLogs(level="ERROR"):
                self.assertFalse(self.manager.start("run"))
        self.assertFalse(self.controller.ctx.is_walk)
        self.assertIsNone(self.manager.active)

    def test_startle_swat_captures_cursor_in_both_directions_and_releases(self):
        from PyQt6.QtCore import QPoint
        ai = self.controller.cursor_ai
        for x in (430, 480):
            with self.subTest(cursor_x=x), patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(x, 550)), patch(
                'pet_cursor_ai.QCursor.setPos'
            ) as move_cursor:
                ai.post_swat_caution_timer.stop()
                ai.finish_post_swat_caution()
                self.pet.animator.force_set_node(N.SIT_IDLE)
                ai.start_rear_startle_swat(QPoint(x, 550))
                self.assertTrue(ai._rear_startle_pending_swat)
                self.assertFalse(ai.cursor_resist_timer.isActive())
                self.reach(N.SWAT)
                step = self.pet.animator.current_step
                self.controller.process_walk_step()
                self.assertIs(self.pet.animator.current_step, step)
                self.assertTrue(self.controller.ctx.is_swat_cursor)
                self.assertTrue(ai.cursor_resist_timer.isActive())
                ai.apply_swat_cursor_resistance()
                move_cursor.assert_called_once()
                self.finish_animation(N.SWAT)
                self.assertFalse(self.controller.ctx.is_swat_cursor)
                self.assertFalse(ai.cursor_resist_timer.isActive())
                ai.apply_swat_cursor_resistance()
                move_cursor.assert_called_once()

    def test_swat_pulls_cursor_once_then_releases_on_last_frame(self):
        from PyQt6.QtCore import QPoint
        ai = self.controller.cursor_ai
        self.pet.animator.force_set_node(N.STAND_IDLE)
        with patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(530, 550)), patch(
            'pet_cursor_ai.QCursor.setPos'
        ) as move_cursor:
            ai.start_cursor_swat()
            self.assertTrue(self.controller.ctx.is_swat_cursor)
            self.assertTrue(ai.cursor_resist_timer.isActive())
            ai.apply_swat_cursor_resistance()
            move_cursor.assert_called_once()
            pulled_x, pulled_y = move_cursor.call_args.args
            self.assertLess(pulled_x, 530)
            self.assertGreater(pulled_y, 550)
            step = self.pet.animator.current_step
            ai.start_cursor_swat()
            self.assertIs(self.pet.animator.current_step, step)
            with patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(900, 10)):
                ai.check_cursor_proximity()
            self.assertTrue(self.controller.ctx.is_swat_cursor)
            self.finish_animation(N.SWAT)
            self.assertFalse(self.controller.ctx.is_swat_cursor)
            self.assertFalse(ai.cursor_resist_timer.isActive())
            self.assertTrue(self.controller.ctx.is_post_swat_cautious)
            ai.apply_swat_cursor_resistance()
            move_cursor.assert_called_once()
            ai.check_cursor_proximity()
            self.assertFalse(self.controller.ctx.is_wait_to_swat)
            self.manager.start('clean')
            scenario = self.manager.active
            self.controller.on_animation_finished(N.SWAT.value)
            self.assertIs(self.manager.active, scenario)

    def test_rear_startle_does_not_restart_first_swat_frames(self):
        ai = self.controller.cursor_ai
        self.pet.animator.force_set_node(N.SWAT)
        step = self.pet.animator.current_step
        ai._rear_startle_pending_swat = True
        ai._activate_swat_after_startle()
        self.assertIs(self.pet.animator.current_step, step)
        self.finish_animation(N.SWAT)
        self.assertFalse(ai.is_busy())

    def test_swat_contact_tracks_actual_paw_pixels_in_both_directions(self):
        from pet_cursor_ai import SWAT_PAW_POINTS
        from PIL import Image
        ai = self.controller.cursor_ai
        self.pet._width = 336
        self.pet.height = lambda: 240
        for index, point in enumerate(SWAT_PAW_POINTS):
            frame = Path(__file__).resolve().parents[1] / 'assets/pixel/swat' / f'{index:03}.png'
            with Image.open(frame) as image:
                self.assertEqual(image.getpixel(point)[3], 255)
            self.pet.animation_player.current_frame_index = index
            self.pet.set_facing_right(True)
            right_x, right_y = ai._get_swat_resist_anchor()
            self.pet.set_facing_right(False)
            left_x, left_y = ai._get_swat_resist_anchor()
            self.assertAlmostEqual(right_x + left_x, 2 * self.pet.x() + 336)
            self.assertEqual(right_y, left_y)
            self.assertAlmostEqual(right_x - self.pet.x(), (point[0] + .5) * 3)
            self.assertAlmostEqual(right_y - self.pet.y(), (point[1] + .5) * 3)

    def test_cursor_follows_fast_paw_motion_without_lag_and_can_escape(self):
        import math
        from PyQt6.QtCore import QPoint
        ai = self.controller.cursor_ai
        self.pet._width = 336
        self.pet.height = lambda: 240
        self.pet.animator.force_set_node(N.SWAT)
        self.controller.ctx.is_swat_cursor = True
        position = [QPoint(self.pet.x() + 318, self.pet.y() + 168)]
        def move(x, y):
            position[0] = QPoint(x, y)
        with patch('pet_cursor_ai.QCursor.pos', side_effect=lambda: position[0]), patch(
            'pet_cursor_ai.QCursor.setPos', side_effect=move
        ) as move_cursor:
            self.pet.animation_player.current_frame_index = 0
            for _ in range(30):
                ai.apply_swat_cursor_resistance()
            for index in range(1, 11):
                self.pet.animation_player.current_frame_index = index
                ai.apply_swat_cursor_resistance()
                x, y = ai._get_swat_resist_anchor()
                self.assertLess(math.hypot(position[0].x() - x, position[0].y() - y), 5)
            position[0] = QPoint(2000, 2000)
            self.pet.animation_player.current_frame_index = 0
            move_cursor.reset_mock()
            ai.apply_swat_cursor_resistance()
            move_cursor.assert_not_called()

    def test_single_file_plugin_is_selected_and_receives_events(self):
        script = '''from behavior_runtime import Scenario
class Behavior(Scenario):
    id = "new_script"
    @classmethod
    def weight(cls, controller): return 100
    def on_start(self): self.events = ["start"]
    def on_tick(self): self.events.append("tick")
    def on_animation_finished(self, node): self.events.append(node.value)
'''
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "new_script.py").write_text(script)
            other = PetController(self.pet, plugin_dirs=[directory])
            try:
                with patch("behavior_runtime.random.random", return_value=1), patch(
                    "behavior_runtime.random.choices", return_value=[other.behaviors.registry["new_script"]]
                ):
                    other.behaviors.logic_tick()
                active = other.behaviors.active
                self.assertEqual(active.id, "new_script")
                other.process_walk_step()
                other.on_animation_finished(N.YAWN.value)
                self.assertEqual(active.events, ["start", "tick", "yawn"])
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
        self.manager.start("clean")
        self.reach(N.CLEAN)
        self.controller.process_walk_step()
        old = self.manager.active
        timer = next(iter(old._timers))
        self.manager.start("sleep")
        self.assertFalse(timer.isActive())
        timer.timeout.emit()  # A queued callback from the previous run is harmless.
        self.assertEqual(self.manager.active.id, "sleep")
        self.assertFalse(self.controller.ctx.is_clean)

    def test_timer_starts_only_after_transition(self):
        self.pet.animator.force_set_node(N.SLEEP)
        self.manager.start("clean")
        self.controller.process_walk_step()
        self.assertFalse(self.manager.active._timers)
        self.reach(N.CLEAN)
        self.controller.process_walk_step()
        self.assertEqual(len(self.manager.active._timers), 1)

    def test_clean_three_phases_finish_on_loop_boundary(self):
        self.manager.start("clean")
        scenario = self.manager.active
        self.assertEqual(self.pet.current_animation_node(), N.START_CLEAN)
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)
        self.finish_animation(N.START_CLEAN)
        self.assertEqual(self.pet.current_animation_node(), N.CLEAN)
        self.controller.process_walk_step()
        timer = next(iter(scenario._timers))
        self.assertGreaterEqual(timer.interval(), 2000)
        self.assertLessEqual(timer.interval(), 5000)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(scenario.phase, "clean")
        self.controller.on_animation_loop_finished(N.CLEAN.value)
        self.assertEqual(scenario.phase, "end")
        self.assertEqual(self.pet.current_animation_node(), N.END_CLEAN)
        self.assertIs(self.manager.active, scenario)
        self.assertTrue(self.controller.ctx.is_clean)
        self.finish_animation(N.END_CLEAN)
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_clean)
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)

    def test_missing_clean_loop_cancels_after_entry(self):
        self.manager.start("clean")
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "clean"):
            with self.assertLogs(level="ERROR"):
                self.finish_animation(N.START_CLEAN)
        self.assertIsNone(self.manager.active)
        self.assertIn("clean", self.manager.disabled)
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)

    def test_missing_clean_exit_does_not_leave_scenario_stuck(self):
        self.manager.start("clean")
        self.reach(N.CLEAN)
        self.controller.process_walk_step()
        self.manager.active._request_finish()
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "end_clean"):
            with self.assertLogs(level="ERROR"):
                self.controller.on_animation_loop_finished(N.CLEAN.value)
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_clean)
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)

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
            flags = ("is_clean",)
            def on_start(self):
                self.later(1000, self.finish)
                raise RuntimeError("test failure")
        self.manager.registry[Broken.id] = Broken
        with self.assertLogs("behavior_runtime", level="ERROR"):
            self.assertFalse(self.manager.start("broken"))
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_clean)
        self.assertFalse(self.manager.start("broken"))

    def test_meow_and_pending_startle_block_autonomy(self):
        self.manager.start("meow")
        self.assertTrue(self.controller.is_busy())
        self.controller.behaviors.logic_tick()
        self.assertEqual(self.manager.active.id, "meow")
        self.finish_animation(N.MEOW)
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
            ai, "start_rear_startle_swat"
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
        self.assertFalse(self.controller.ctx.is_sleep)
        self.assertFalse(self.controller.start_behavior("clean"))
        self.controller.on_mouse_release()
        self.assertEqual(self.pet.current_state, PetState.RECOVER)
        self.finish_animation(N.RECOVER)
        self.assertEqual(self.pet.current_state, PetState.IDLE)
        self.assertFalse(self.controller.ctx.is_recover)

    def test_release_drag_plays_fall_once_and_lands_only_on_ground(self):
        from animation_graph import NODE_META
        self.pet.move(self.pet.x(), self.pet.ground_y - 200)
        self.controller.on_mouse_press(QPointF(400, 300))
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)
        self.assertTrue(NODE_META[N.DRAG].loop)
        self.assertFalse(self.controller.ctx.is_fall)
        self.controller.on_mouse_release()
        self.assertEqual(self.pet.current_animation_node(), N.FALL)
        self.assertFalse(NODE_META[N.FALL].loop)
        self.assertTrue(self.controller.ctx.is_fall)
        step = self.pet.animator.current_step
        self.controller.on_mouse_release()
        self.assertIs(self.pet.animator.current_step, step)
        self.finish_animation(N.FALL)
        self.assertEqual(self.pet.current_animation_node(), N.FALL)
        self.assertTrue(self.controller.ctx.is_fall)
        self.assertFalse(self.controller.ctx.is_recover)
        for _ in range(100):
            self.controller.motion.apply_gravity()
            if self.controller.ctx.is_recover:
                break
        self.assertEqual(self.pet.y(), self.pet.ground_y)
        self.assertEqual(self.pet.current_animation_node(), N.RECOVER)
        self.finish_animation(N.RECOVER)
        self.assertFalse(self.controller.interaction_locked)

    def test_regrab_during_fall_returns_to_calm_loop_without_position_jump(self):
        self.pet.move(400, self.pet.ground_y - 200)
        self.controller.start_fall()
        self.controller.motion.apply_gravity()
        y = self.pet.y()
        self.controller.on_mouse_press(QPointF(400, y))
        self.assertEqual(self.pet.y(), y)
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)
        self.assertTrue(self.controller.ctx.is_drag)
        self.assertFalse(self.controller.ctx.is_fall)
        self.controller.on_animation_finished(N.FALL.value)
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)

    def test_menu_preserves_hide_and_close_does_not_cancel_it(self):
        self.manager.start("hide")
        active = self.manager.active
        self.controller.start_menu_meow()
        self.assertIs(self.manager.active, active)
        self.assertTrue(self.controller.ctx.is_menu_open)
        self.controller.finish_menu_meow()
        self.assertIs(self.manager.active, active)

    def test_menu_replays_meow_and_releases_on_close(self):
        self.controller.start_menu_meow()
        self.finish_animation(N.MEOW)
        self.assertEqual(self.pet.current_animation_node(), N.MEOW)
        self.assertIsNotNone(self.pet.animator.current_step)
        self.controller.finish_menu_meow()
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_meow)

    def begin_hide_peek(self, edge="left"):
        self.manager.start("hide")
        self.reach(N.RUN)
        scenario = self.manager.active
        scenario.edge = edge
        self.controller.motion.stop_horizontal_motion()
        self.controller.process_walk_step()
        self.assertEqual(scenario.phase, "hidden")
        self.assertFalse(self.pet.visible)
        timer = next(iter(scenario._timers))
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(scenario.phase, "start")
        return scenario

    def test_hide_entry_loop_exit_and_ground_return(self):
        scenario = self.begin_hide_peek()
        self.assertEqual(self.pet.current_animation_node(), N.START_HIDE)
        self.assertTrue(self.pet.visible)
        self.assertEqual(self.pet.anchor, "left")
        self.assertFalse(scenario._timers)
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)  # Entry doesn't consume watching time.
        self.finish_animation(N.START_HIDE)
        self.assertEqual(self.pet.current_animation_node(), N.HIDE)
        self.assertEqual(scenario.phase, "hide")
        timer = next(iter(scenario._timers))
        self.assertGreaterEqual(timer.interval(), 5000)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(scenario.phase, "end")
        self.assertEqual(self.pet.current_animation_node(), N.END_HIDE)
        self.assertTrue(self.pet.visible)  # Tail must finish before disappearing.
        self.finish_animation(N.END_HIDE)
        self.assertEqual(scenario.phase, "return")
        self.assertFalse(self.pet.visible)
        timer = next(iter(scenario._timers))
        timer.stop()
        timer.timeout.emit()
        self.assertIs(self.manager.active, scenario)
        self.assertEqual(scenario.phase, "enter")
        self.assertEqual(self.pet.x(), -self.pet.width())
        self.assertTrue(self.pet.visible)
        self.assertEqual(self.pet.y(), self.pet.ground_y)
        self.assertIsNone(self.pet.anchor)
        self.assertEqual(self.pet.current_animation_node(), N.RUN)
        for _ in range(100):
            self.controller.process_walk_step()
            if self.manager.active is None:
                break
        self.assertIsNone(self.manager.active)
        self.assertIsNone(self.pet.screen_clip)
        self.reach(N.SIT_IDLE)

    def test_enter_reveals_gradually_from_both_edges_on_offset_screen(self):
        self.pet.get_current_screen_rect = lambda: QRect(-1000, -100, 1000, 700)
        self.pet.clamp_position = lambda x, y: (max(-1000, min(x, -self.pet.width())), y)
        for edge in ('left', 'right'):
            with self.subTest(edge=edge), patch('pet_motion.random.choice', return_value=edge):
                self.manager.start('enter')
                screen = self.pet.get_current_screen_rect()
                widths = []
                for _ in range(100):
                    visible = QRect(self.pet.x(), self.pet.y(), self.pet.width(), self.pet.height()).intersected(screen)
                    widths.append(visible.width())
                    before = self.pet.x()
                    self.controller.process_walk_step()
                    self.assertLessEqual(abs(self.pet.x() - before), self.controller.ctx.walk_speed)
                    if self.manager.active is None:
                        break
                self.assertEqual(widths[0], 0)
                self.assertTrue(any(0 < width < self.pet.width() for width in widths))
                self.assertEqual(widths, sorted(widths))
                self.assertIsNone(self.manager.active)
                self.assertIsNone(self.pet.screen_clip)

    def test_cancel_enter_clears_clip_and_restores_accessible_position(self):
        with patch('pet_motion.random.choice', return_value='left'):
            self.manager.start('enter')
        self.assertLess(self.pet.x(), 0)
        self.manager.start('clean')
        self.assertIsNone(self.pet.screen_clip)
        self.assertFalse(self.controller.ctx.is_walk)
        self.assertGreaterEqual(self.pet.x(), 0)

    def test_hide_right_edge_mirrors_and_drag_cancels_watch_timer(self):
        scenario = self.begin_hide_peek("right")
        self.assertFalse(self.pet.animation_player.facing_right)
        self.assertEqual(self.pet.x(), 1000 - self.pet.width())
        self.finish_animation(N.START_HIDE)
        timer = next(iter(scenario._timers))
        self.controller.on_mouse_press(QPointF(self.pet.x(), self.pet.y()))
        self.assertFalse(timer.isActive())
        timer.timeout.emit()
        self.assertTrue(self.controller.ctx.is_drag)
        self.assertIsNone(self.pet.anchor)
        self.assertIsNone(self.manager.active)

    def test_scratch_uses_entry_and_exit_without_repeating_entry_in_loop(self):
        self.manager.start("beg_food")
        scenario = self.manager.active
        self.reach(N.START_SCRATCH_SCREEN)
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)
        self.finish_animation(N.START_SCRATCH_SCREEN)
        self.assertEqual(self.pet.current_animation_node(), N.SCRATCH_SCREEN)
        self.controller.process_walk_step()
        self.assertEqual(len(scenario._timers), 1)
        scenario.finish()
        self.assertEqual(self.pet.current_animation_node(), N.END_SCRATCH_SCREEN)
        self.finish_animation(N.END_SCRATCH_SCREEN)
        self.reach(N.SIT_IDLE)

    def test_poop_waits_for_its_timer_and_dig_transition(self):
        self.manager.start("poop")
        self.reach(N.RUN)
        self.controller.motion.stop_horizontal_motion()
        self.controller.process_walk_step()
        self.reach(N.POOP)
        self.controller.process_walk_step()
        scenario = self.manager.active
        self.finish_animation(N.POOP)
        self.assertEqual(self.pet.current_animation_node(), N.POOP)
        self.assertEqual(scenario.phase, "poop")
        timer = next(iter(scenario._timers))
        self.assertEqual(timer.interval(), 5000)
        self.controller.on_animation_loop_finished(N.POOP.value)
        self.assertEqual(self.pet.current_animation_node(), N.POOP)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(self.pet.current_animation_node(), N.POOP)
        self.controller.on_animation_loop_finished(N.POOP.value)
        self.assertEqual(self.pet.current_animation_node(), N.END_POOP)
        self.finish_animation(N.END_POOP)
        self.reach(N.START_DIG)
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)
        self.reach(N.DIG)
        self.controller.process_walk_step()
        self.assertEqual(scenario.phase, "dig")
        timer = next(iter(scenario._timers))
        self.assertGreaterEqual(timer.interval(), 1500)
        self.assertLessEqual(timer.interval(), 2500)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(scenario.phase, "dig")
        self.assertEqual(self.manager.active.id, "poop")
        self.controller.on_animation_loop_finished(N.DIG.value)
        self.assertEqual(self.pet.current_animation_node(), N.END_DIG)
        self.assertEqual(self.manager.active.id, "poop")
        self.assertTrue(self.controller.ctx.is_poop)
        self.finish_animation(N.END_DIG)
        self.assertEqual(self.manager.active.id, "run")
        self.assertFalse(self.controller.ctx.is_poop)

    def start_notification_dig(self):
        self.manager.start("inspect_notifications")
        self.reach(N.ALERT)
        self.finish_animation(N.ALERT)
        self.reach(N.RUN)
        self.controller.motion.stop_horizontal_motion()
        self.controller.process_walk_step()
        scenario = self.manager.active
        self.reach(N.START_DIG)
        self.controller.process_walk_step()
        self.assertFalse(scenario._timers)
        self.finish_animation(N.START_DIG)
        self.controller.process_walk_step()
        return scenario

    def test_inspect_notifications_dig_waits_for_boundary_and_full_exit(self):
        scenario = self.start_notification_dig()
        timer = next(iter(scenario._timers))
        self.assertGreaterEqual(timer.interval(), 2000)
        self.assertLessEqual(timer.interval(), 4000)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(self.pet.current_animation_node(), N.DIG)
        self.controller.on_animation_loop_finished(N.DIG.value)
        self.assertEqual(self.pet.current_animation_node(), N.END_DIG)
        self.assertIs(self.manager.active, scenario)
        self.finish_animation(N.END_DIG)
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_inspect_notifications)
        self.reach(N.SIT_IDLE)

    def test_missing_dig_exit_releases_scenario(self):
        scenario = self.start_notification_dig()
        scenario._request_finish_dig()
        with patch.object(self.pet.animation_player, "set_animation", side_effect=lambda name, **kw: name != "end_dig"):
            with self.assertLogs(level="ERROR"):
                self.controller.on_animation_loop_finished(N.DIG.value)
        self.assertIsNone(self.manager.active)
        self.assertFalse(self.controller.ctx.is_inspect_notifications)
        self.assertEqual(self.pet.current_animation_node(), N.SIT_IDLE)

    def test_canceled_dig_timer_cannot_stop_new_scenario(self):
        scenario = self.start_notification_dig()
        timer = next(iter(scenario._timers))
        self.manager.start("clean")
        active = self.manager.active
        step = self.pet.animator.current_step
        self.assertFalse(timer.isActive())
        timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.DIG.value)
        self.assertIs(self.manager.active, active)
        self.assertIs(self.pet.animator.current_step, step)

    def test_zero_distance_run_on_small_screen(self):
        self.pet._width = 1000
        self.pet._x = 0
        self.manager.start("run")
        self.reach(N.RUN)
        self.controller.process_walk_step()
        self.assertEqual(self.manager.active.phase, "wait")
        self.assertFalse(self.controller.ctx.is_walk)

    def test_eat_completes_before_due_poop(self):
        self.manager._next_due["poop"] = 0
        self.assertTrue(self.controller.try_feed())
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "eat")
        self.reach(N.EAT)
        self.finish_eating()
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "eat")
        self.reach(N.CLEAN)
        self.controller.process_walk_step()
        self.manager.active._request_finish()
        self.controller.on_animation_loop_finished(N.CLEAN.value)
        self.finish_animation(N.END_CLEAN)
        deadline = self.manager._next_due["poop"]
        self.manager._clock = lambda: deadline
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "poop")
        self.assertNotIn("poop", self.manager._next_due)

    def test_poop_only_scheduled_after_food_is_consumed(self):
        self.assertNotIn("poop", self.manager._next_due)
        self.manager._clock = lambda: 100
        self.assertTrue(self.controller.try_feed())
        self.assertNotIn("poop", self.manager._next_due)
        self.reach(N.EAT)
        self.finish_eating()
        self.assertEqual(self.manager._next_due["poop"], 160)
        self.manager.request_once("poop", 60)
        self.assertEqual(self.manager._next_due["poop"], 160)
        self.manager._clock = lambda: 120
        self.manager.request_once("poop", 60)
        self.assertEqual(self.manager._next_due["poop"], 160)

    def test_poop_retries_every_thirty_seconds_while_busy(self):
        self.manager._clock = lambda: 100
        self.manager._next_due = {"poop": 100}
        self.manager.start("clean")
        self.manager.logic_tick()
        self.assertEqual(self.manager._next_due["poop"], 130)
        self.controller.start_idle()
        with patch.object(self.manager, "_score", return_value=0):
            self.manager._clock = lambda: 129
            self.manager.logic_tick()
            self.assertIsNone(self.manager.active)
        self.manager._clock = lambda: 130
        self.manager.logic_tick()
        self.assertEqual(self.manager.active.id, "poop")
        self.assertNotIn("poop", self.manager._next_due)

    def test_eat_waits_five_seconds_and_finishes_on_loop_boundary(self):
        self.manager._clock = lambda: 100
        self.assertTrue(self.controller.try_feed())
        scenario = self.manager.active
        self.assertFalse(scenario._timers)
        self.reach(N.EAT)
        self.controller.process_walk_step()
        timer = next(iter(scenario._timers))
        self.assertEqual(timer.interval(), 5000)
        self.controller.on_animation_loop_finished(N.EAT.value)
        self.assertEqual(scenario.phase, "eat")
        self.assertNotIn("poop", self.manager._next_due)
        timer.stop()
        timer.timeout.emit()
        self.assertEqual(scenario.phase, "eat")
        self.assertFalse(scenario.consumed)
        self.manager._clock = lambda: 105
        self.controller.on_animation_loop_finished(N.EAT.value)
        self.assertTrue(scenario.consumed)
        self.assertEqual(self.manager._next_due["poop"], 165)
        self.reach(N.CLEAN)
        self.assertTrue(self.controller.ctx.is_clean)

    def test_cancel_eat_loop_removes_timer_and_does_not_schedule_poop(self):
        self.assertTrue(self.controller.try_feed())
        self.reach(N.EAT)
        self.controller.process_walk_step()
        timer = next(iter(self.manager.active._timers))
        self.controller.start_idle()
        self.assertFalse(timer.isActive())
        timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.EAT.value)
        self.assertNotIn("poop", self.manager._next_due)
        self.assertFalse(self.controller.ctx.is_eat)

    def test_food_uses_meow_then_clean_and_ignores_food_for_a_minute(self):
        now = [100.0]
        self.manager._clock = lambda: now[0]
        self.assertTrue(self.controller.try_feed())
        scenario = self.manager.active
        self.assertFalse(self.controller.ctx.is_clean)
        self.reach(N.EAT)
        self.finish_eating()
        self.reach(N.CLEAN)
        self.assertTrue(self.controller.ctx.is_clean)
        self.assertFalse(self.controller.try_feed())
        self.assertIs(self.manager.active, scenario)
        self.controller.process_walk_step()
        scenario._request_finish()
        self.controller.on_animation_loop_finished(N.CLEAN.value)
        now[0] = 105.0
        self.finish_animation(N.END_CLEAN)
        self.assertFalse(self.controller.ctx.is_eat)
        self.assertFalse(self.controller.ctx.is_clean)
        self.assertEqual(self.controller.food_cooldown_until, 165.0)
        now[0] = 164.99
        self.assertFalse(self.controller.try_feed())
        now[0] = 165.0
        self.assertTrue(self.controller.try_feed())

    def test_cancel_after_chewing_cancels_wash_and_keeps_food_cooldown(self):
        self.manager._clock = lambda: 100.0
        self.controller.try_feed()
        self.reach(N.EAT)
        self.finish_eating()
        self.controller.start_menu_meow()
        active = self.manager.active
        self.controller.on_animation_finished(N.END_CLEAN.value)
        self.assertIs(self.manager.active, active)
        self.assertEqual(self.controller.food_cooldown_until, 160.0)
        self.assertEqual(self.manager.registry['eat'].weight(self.controller), 0)

    def test_stop_cancels_all_owned_timers(self):
        self.controller.start()
        self.manager.start("run")
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
        self.animator.force_set_node(N.RUN)
        self.animator.play_sequence_nodes([N.RUN, N.STAND_IDLE], force_restart=True)
        self.assertEqual(self.animator.current_node, N.RUN)
        self.animator.notify_motion_complete()
        self.assertEqual(self.animator.current_node, N.STAND_IDLE)

    def test_initial_bridge_progresses(self):
        self.animator.current_node = None
        self.animator.current_step = None
        self.animator.play_sequence_nodes([N.SIT_IDLE, N.MEOW])
        self.assertTrue(self.animator.bridge_timer.isActive())
        self.animator._on_bridge_timeout()
        self.assertEqual(self.animator.current_node, N.MEOW)

    def test_append_uses_queue_tail(self):
        self.animator.play_sequence_nodes([N.MEOW, N.SLEEP], force_restart=True)
        self.animator.play_sequence_nodes([N.CLEAN], replace=False)
        nodes = [step.node for step in self.animator.expanded_queue]
        sleep_index = nodes.index(N.SLEEP)
        self.assertEqual(nodes[sleep_index + 1], N.SIT_UP)
        self.assertFalse(self.animator.expanded_queue[sleep_index].hold)

    def test_repeated_one_shot_keeps_new_step(self):
        self.animator.play_sequence_nodes([N.MEOW, N.MEOW], force_restart=True)
        self.animator.on_animation_finished(N.MEOW.value)
        self.assertIsNotNone(self.animator.current_step)

    def test_clear_and_force_set_release_interrupt(self):
        self.animator.interrupt_with(N.FALL)
        self.animator.clear()
        self.assertFalse(self.animator.is_interrupt_active)
        self.animator.interrupt_with(N.FALL)
        self.animator.force_set_node(N.SIT_IDLE)
        self.assertFalse(self.animator.is_interrupt_active)


class PlayerTests(unittest.TestCase):
    def test_turn_does_not_restart_one_shot(self):
        player = AnimationPlayer("unused")
        player.timer.stop()
        frames = [QPixmap(1, 1) for _ in range(3)]
        with patch.object(player, "_load_frames", return_value=frames):
            player.set_animation("eat", loop=False)
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
