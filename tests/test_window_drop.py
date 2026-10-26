"""Top-of-screen entrances and deferred desktop-only interactions."""
from unittest.mock import patch
import unittest

from test_behaviors import N
import test_surfaces as fixtures
from surfaces import Rect, Window


class WindowDropTests(unittest.TestCase):
    setUp = fixtures.BindingTests.setUp
    tearDown = fixtures.BindingTests.tearDown
    attach = fixtures.BindingTests.attach

    def test_food_poop_request_retries_after_failed_or_canceled_descent(self):
        self.attach()
        manager = self.controller.behaviors
        now = [1000]
        manager._clock = lambda: now[0]
        manager._next_due = {'poop': 1000}
        with patch('surface_controller.random.random', return_value=1), patch.object(
            manager, '_score', return_value=0
        ):
            manager.logic_tick()
            self.assertEqual(manager._next_due['poop'], 1030)
            now[0] = 1029
            manager.logic_tick()
            self.assertFalse(self.surfaces.travel.active)
        now[0] = 1030
        with patch('surface_controller.random.random', return_value=0):
            manager.logic_tick()
        self.assertTrue(self.surfaces.travel.active)
        self.assertEqual(self.surfaces.travel.after_behavior, 'poop')
        self.assertEqual(manager._next_due['poop'], 1060)
        self.surfaces.travel.cancel()
        self.controller.motion.stop_horizontal_motion()
        self.assertEqual(manager._next_due['poop'], 1060)

    def reach_hidden(self):
        self.assertTrue(self.controller.start_behavior('window_drop'))
        scenario = self.controller.behaviors.active
        self.pet.force_set_animation_node(N.RUN)
        for _ in range(1000):
            self.controller.process_walk_step()
            if scenario.phase == 'hidden':
                break
        self.assertEqual(scenario.phase, 'hidden')
        self.assertFalse(self.pet.isVisible())
        return scenario

    def drop(self, scenario):
        timer = next(iter(scenario._timers))
        timer.stop()
        timer.timeout.emit()

    def test_window_drop_runs_out_reveals_fall_and_finishes_after_landing(self):
        scenario = self.reach_hidden()
        self.drop(scenario)
        self.assertEqual(scenario.phase, 'fall')
        self.assertTrue(self.pet.isVisible())
        self.assertEqual(self.pet.y(), -self.pet.height())
        self.assertIsNotNone(self.pet.screen_clip)
        self.assertEqual(self.pet.current_animation_node(), N.FALL)
        ys = []
        while self.controller.ctx.is_fall:
            self.controller.process_walk_step()
            self.controller.motion.apply_gravity()
            ys.append(self.pet.y())
        self.assertEqual(ys, sorted(ys))
        self.assertTrue(any(-self.pet.height() < y < 0 for y in ys))
        self.assertEqual(self.pet.y(), 250)
        self.assertTrue(self.controller.surfaces.on_window)
        self.pet.animator.on_animation_finished(N.RECOVER.value)
        self.controller.on_animation_finished(N.RECOVER.value)
        self.assertIsNone(self.controller.behaviors.active)
        self.assertIsNone(self.pet.screen_clip)

    def test_window_drop_requires_mode_floor_and_an_open_vertical_path(self):
        self.surfaces.set_enabled(False)
        self.assertFalse(self.controller.start_behavior('window_drop'))
        self.surfaces.set_enabled(True)
        self.attach()
        self.assertFalse(self.controller.start_behavior('window_drop'))
        self.surfaces.detach()
        self.pet.move(400, 500)
        self.tracker.windows.insert(0, Window(2, Rect(0, 20, 1000, 200)))
        self.surfaces.refresh()
        self.assertFalse(self.surfaces.top_entries())
        self.assertFalse(self.controller.start_behavior('window_drop'))

    def test_target_disappears_while_hidden_returns_from_side_instead(self):
        scenario = self.reach_hidden()
        self.tracker.windows.clear()
        self.drop(scenario)
        self.assertEqual(scenario.phase, 'return')
        self.assertFalse(self.controller.ctx.is_fall)
        self.assertTrue(self.pet.isVisible())
        for _ in range(1000):
            self.controller.process_walk_step()
            if self.controller.behaviors.active is None:
                break
        self.assertIsNone(self.controller.behaviors.active)
        self.assertIsNone(self.pet.screen_clip)
        self.assertEqual(self.pet.y(), 500)

    def test_cancel_hidden_run_restores_visible_pet_and_owns_no_late_callback(self):
        scenario = self.reach_hidden()
        self.controller.start_idle()
        self.assertTrue(self.pet.isVisible())
        self.assertIsNone(self.pet.screen_clip)
        self.assertFalse(scenario._timers)
        self.assertFalse(self.controller.ctx.is_hidden_offscreen)

    def test_target_lost_during_top_entry_falls_to_desktop(self):
        scenario = self.reach_hidden()
        self.drop(scenario)
        self.tracker.windows.clear()
        self.surfaces.refresh()
        self.assertEqual(self.pet.ground_y, 500)
        while self.controller.ctx.is_fall:
            self.controller.motion.apply_gravity()
        self.pet.animator.on_animation_finished(N.RECOVER.value)
        self.controller.on_animation_finished(N.RECOVER.value)
        self.assertIsNone(self.controller.behaviors.active)
        self.assertEqual(self.pet.y(), 500)
        self.assertIsNone(self.pet.screen_clip)

    def test_disable_during_top_entry_clears_scenario_and_returns_to_desktop(self):
        scenario = self.reach_hidden()
        self.drop(scenario)
        self.surfaces.set_enabled(False)
        self.controller.process_walk_step()
        self.assertIsNone(self.controller.behaviors.active)
        self.assertIsNone(self.pet.screen_clip)
        while self.controller.ctx.is_fall:
            self.controller.motion.apply_gravity()
        self.assertEqual(self.pet.y(), 500)

    def test_deferred_desktop_interaction_chance_boundary_and_no_repeated_reroll(self):
        self.attach()
        manager = self.controller.behaviors
        manager._clock = lambda: 1000
        manager._next_due = {'hide': 0}
        with patch('surface_controller.random.random', return_value=.20) as roll, patch.object(
            manager, '_score', return_value=0
        ):
            manager.logic_tick()
            manager.logic_tick()
            self.assertEqual(roll.call_count, 1)
        self.assertFalse(self.surfaces.travel.active)
        self.assertGreater(manager._next_due['hide'], 1000)
        with patch('surface_controller.random.random', return_value=.199):
            self.assertTrue(manager.start('hide'))
        self.assertTrue(self.surfaces.travel.active)
        self.assertEqual(self.surfaces.travel.after_behavior, 'hide')
        self.assertIsNone(manager.active)

    def test_deferred_action_starts_once_only_after_actual_desktop_landing(self):
        self.attach()
        with patch('surface_controller.random.random', return_value=0):
            self.assertTrue(self.controller.start_behavior('hide'))
        self.pet.force_set_animation_node(N.WALK)
        for _ in range(1000):
            self.controller.process_walk_step()
            if self.surfaces.travel.phase == 'jump':
                break
        self.assertEqual(self.surfaces.travel.phase, 'jump')
        self.assertIsNone(self.controller.behaviors.active)
        self.now += .35
        self.surfaces.tick()
        self.controller.on_animation_finished(N.JUMP.value)
        self.now += .5
        self.surfaces.tick()
        scenario = self.controller.behaviors.active
        self.assertEqual(scenario.id, 'hide')
        self.assertEqual(self.pet.y(), 500)
        self.assertFalse(self.surfaces.elevated)
        self.assertIsNone(self.surfaces.travel.after_behavior)
        self.controller.on_animation_finished(N.JUMP.value)
        self.assertIs(self.controller.behaviors.active, scenario)

    def test_cancel_descent_forgets_pending_action(self):
        from PyQt6.QtCore import QPointF
        self.attach()
        with patch('surface_controller.random.random', return_value=0):
            self.assertTrue(self.controller.start_behavior('hide'))
        self.controller.on_mouse_press(QPointF(300, 250))
        self.assertIsNone(self.surfaces.travel.after_behavior)
        self.controller.on_animation_finished(N.JUMP.value)
        self.assertIsNone(self.controller.behaviors.active)

    def test_no_safe_jump_skips_interaction_without_moving_pet(self):
        self.attach()
        position = self.pet.x(), self.pet.y()
        with patch('surface_controller.random.random', return_value=0), patch.object(
            self.surfaces.navigator, 'plan', return_value=None
        ):
            self.assertFalse(self.controller.start_behavior('hide'))
        self.assertEqual((self.pet.x(), self.pet.y()), position)
        self.assertFalse(self.surfaces.travel.active)

    def test_descent_for_action_ignores_support_window_and_needs_no_headroom(self):
        self.tracker.windows = [Window(1, Rect(200, 100, 800, 550))]
        self.surfaces.refresh()
        source = next(p for p in self.surfaces.snapshot.platforms if p.window == 1)
        self.pet.move(300, 0)
        self.surfaces.attach(source)
        with patch('surface_controller.random.random', return_value=0):
            self.assertTrue(self.controller.start_behavior('hide'))
        self.pet.force_set_animation_node(N.WALK)
        for _ in range(1000):
            self.controller.process_walk_step()
            if self.surfaces.travel.phase == 'jump':
                break
        self.assertEqual(self.surfaces.travel.phase, 'jump')
        self.now += .8
        self.controller.on_animation_finished(N.JUMP.value)
        self.surfaces.tick()
        self.assertEqual(self.pet.y(), 500)
        self.assertEqual(self.controller.behaviors.active.id, 'hide')

    def test_other_foreground_windows_still_block_descent(self):
        self.tracker.windows = [Window(2, Rect(0, 150, 1000, 600)),
                                Window(1, Rect(200, 100, 800, 550))]
        self.surfaces.refresh()
        source = next(p for p in self.surfaces.snapshot.platforms if p.window == 1)
        self.pet.move(300, 0)
        self.surfaces.attach(source)
        with patch('surface_controller.random.random', return_value=0):
            self.assertFalse(self.controller.start_behavior('hide'))
        self.assertFalse(self.surfaces.travel.active)
