"""Cursor movement is mocked: these tests never move the user's mouse."""
import unittest
from unittest.mock import patch

from test_behaviors import APP, FakePet, N
from animation_graph import NODE_META
from pet_controller import PetController
from PyQt6.QtCore import QPoint, QPointF, QTimer


class JumpTests(unittest.TestCase):
    def setUp(self):
        self.pet = FakePet()
        self.controller = PetController(self.pet, plugin_dirs=[])
        self.ai = self.controller.cursor_ai
        self.jump = self.ai.jump
        self.now = 1000.0
        self.jump.clock = lambda: self.now
        self.cursor = patch('cursor_jump.QCursor.pos', return_value=QPoint(700, 550)).start()
        self.move_cursor = patch('cursor_jump.QCursor.setPos').start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.controller.stop()
        self.controller.deleteLater()
        APP.processEvents()

    def finish(self, node):
        self.pet.animator.on_animation_finished(node.value)
        self.controller.on_animation_finished(node.value)

    def reach(self, node):
        for _ in range(30):
            if self.pet.current_animation_node() == node:
                return
            step = self.pet.animator.current_step
            self.assertIsNotNone(step)
            meta = NODE_META[step.node]
            self.assertFalse(meta.requires_motion)
            if meta.loop:
                self.pet.animator._on_bridge_timeout()
            else:
                self.finish(step.node)
        self.fail(f'Could not reach {node}')

    def approach(self):
        self.pet.animator.force_set_node(N.STAND_IDLE)
        self.assertTrue(self.ai.start_cursor_hunt())
        self.reach(N.SNEAK)
        for _ in range(200):
            self.ai.process_chase_step()
            if self.ai._hunt_exit_target is not None:
                break
        self.assertEqual(self.ai._hunt_exit_target, 'jump')
        cursor_x = self.cursor.return_value.x()
        front_x = (self.pet.x() + self.pet.width() - self.controller.ctx.cursor_front_gap
                   if self.pet.animation_player.facing_right
                   else self.pet.x() + self.controller.ctx.cursor_front_gap)
        self.assertEqual(abs(cursor_x - front_x), self.controller.ctx.hunt_standoff_distance)
        self.assertFalse(self.jump.active)
        self.assertEqual(self.pet.current_animation_node(), N.END_SNEAK)
        exit_step = self.pet.animator.current_step
        self.ai.process_chase_step()
        self.controller.on_animation_loop_finished(N.SNEAK.value)
        self.assertIs(self.pet.animator.current_step, exit_step)
        self.assertEqual(self.pet.current_animation_node(), N.END_SNEAK)
        self.finish(N.END_SNEAK)

    def begin_jump(self):
        self.approach()
        self.reach(N.JUMP)
        self.ai.process_chase_step()
        self.assertEqual(self.jump.phase, 'jump')

    def land(self):
        self.begin_jump()
        self.finish(N.JUMP)
        self.assertTrue(self.jump.holding)
        self.landing_anchor = self.jump.paw_anchor()
        self.reach(N.DIG)
        self.ai.process_chase_step()
        self.assertEqual(self.jump.phase, 'dig')

    def test_full_hunt_capture_dig_and_sixty_second_cooldown(self):
        self.land()
        self.move_cursor.assert_called_once_with(*self.landing_anchor)
        self.assertEqual(self.pet.y(), self.pet.ground_y)
        self.assertTrue(self.ai.cursor_resist_timer.isActive())
        self.jump.release_timer.timeout.emit()
        self.assertFalse(self.jump.holding)
        self.assertFalse(self.ai.cursor_resist_timer.isActive())
        self.jump.dig_timer.timeout.emit()
        self.assertEqual(self.pet.current_animation_node(), N.DIG)
        self.controller.on_animation_loop_finished(N.DIG.value)
        self.assertEqual(self.pet.current_animation_node(), N.END_DIG)
        self.assertTrue(self.controller.is_busy())
        self.finish(N.END_DIG)
        self.assertFalse(self.jump.active)
        self.assertFalse(self.controller.ctx.is_hunt_cursor)
        self.assertTrue(self.jump.on_cooldown)
        self.assertFalse(self.ai.start_cursor_hunt())
        self.ai.check_cursor_proximity()
        self.assertFalse(self.controller.ctx.is_wait_to_swat)
        self.controller._reset_motion_flags()  # Other actions don't reset cooldown.
        self.now += 59.9
        self.assertTrue(self.jump.on_cooldown)
        self.now += .2
        self.assertTrue(self.ai.start_cursor_hunt())

    def test_jump_has_windup_arc_and_landing_in_both_directions(self):
        for target_x in [700, 200]:
            with self.subTest(target_x=target_x):
                self.controller._reset_motion_flags()
                self.pet.move(400, self.pet.ground_y)
                self.cursor.return_value = QPoint(target_x, 550)
                self.begin_jump()
                start = self.pet.x()
                duration = self.jump.jump_duration
                started = self.jump.jump_started
                self.now = started + duration / 11
                self.ai.process_chase_step()
                self.assertEqual(self.pet.x(), start)
                self.assertEqual(self.pet.y(), self.pet.ground_y)
                self.now = started + duration * 4.5 / 11
                self.ai.process_chase_step()
                self.assertLess(self.pet.y(), self.pet.ground_y)
                self.assertAlmostEqual(self.pet.x(), (start + self.jump.landing_x) / 2, delta=1)
                self.now = started + duration * 8 / 11
                self.ai.process_chase_step()
                self.assertEqual(self.pet.x(), self.jump.landing_x)
                self.assertEqual(self.pet.y(), self.pet.ground_y)
        self.move_cursor.assert_not_called()

    def test_mouse_drag_in_flight_preserves_position_and_cancels_capture(self):
        self.begin_jump()
        self.now += self.jump.jump_duration * 4.5 / 11
        self.ai.process_chase_step()
        y = self.pet.y()
        self.assertLess(y, self.pet.ground_y)
        self.controller.on_mouse_press(QPointF(self.pet.x(), y))
        self.assertEqual(self.pet.y(), y)
        self.assertTrue(self.controller.ctx.is_drag)
        self.assertFalse(self.jump.active)
        self.jump.release_timer.timeout.emit()
        self.jump.dig_timer.timeout.emit()
        self.controller.on_animation_finished(N.JUMP.value)
        self.move_cursor.assert_not_called()
        self.assertEqual(self.pet.current_animation_node(), N.DRAG)

    def test_menu_cancels_capture_and_late_callbacks_are_harmless(self):
        self.land()
        self.controller.start_menu_meow()
        active = self.controller.behaviors.active
        self.assertEqual(active.id, 'menu_meow')
        self.assertFalse(self.jump.holding)
        self.assertTrue(self.jump.on_cooldown)
        self.jump.release_timer.timeout.emit()
        self.jump.dig_timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.DIG.value)
        self.controller.on_animation_finished(N.END_DIG.value)
        self.assertIs(self.controller.behaviors.active, active)
        self.assertFalse(self.ai.cursor_resist_timer.isActive())

    def test_missing_jump_cancels_without_moving_mouse(self):
        self.approach()
        with patch.object(self.pet.animation_player, 'set_animation', side_effect=lambda name, **kw: name != 'jump'):
            with self.assertLogs(level='ERROR'):
                self.pet.animator._on_bridge_timeout()
        self.assertFalse(self.jump.active)
        self.assertFalse(self.controller.is_busy())
        self.move_cursor.assert_not_called()

    def test_missing_dig_exit_releases_mouse_and_stops_timers(self):
        self.land()
        self.jump.dig_timer.timeout.emit()
        with patch.object(self.pet.animation_player, 'set_animation', side_effect=lambda name, **kw: name != 'end_dig'):
            with self.assertLogs(level='ERROR'):
                self.controller.on_animation_loop_finished(N.DIG.value)
        self.assertFalse(self.jump.active)
        self.assertFalse(self.jump.holding)
        self.assertFalse(any(t.isActive() for t in self.jump.findChildren(QTimer)))
        self.assertFalse(self.ai.cursor_resist_timer.isActive())

    def test_landing_anchor_stays_on_screen_near_edges(self):
        for target_x, start_x in [(5, 100), (995, 800)]:
            self.pet.move(start_x, self.pet.ground_y)
            self.pet.animator.force_set_node(N.STAND_IDLE)
            self.cursor.return_value = QPoint(target_x, 550)
            self.assertTrue(self.jump.start())
            self.reach(N.JUMP)
            self.finish(N.JUMP)
            self.assertTrue(self.pet.get_current_screen_rect().contains(QPoint(*self.jump.paw_anchor())))
            self.jump.cancel()
            self.jump.cooldown_until = 0

    def test_mouse_spring_uses_front_paws_and_stops_after_release(self):
        self.land()
        x, y = self.jump.paw_anchor()
        self.cursor.return_value = QPoint(x + 70, y)
        self.ai.apply_swat_cursor_resistance()
        last_x, last_y = self.move_cursor.call_args.args
        self.assertLess(last_x, x + 70)
        self.assertEqual(last_y, y)
        self.jump.release()
        calls = self.move_cursor.call_count
        self.ai.apply_swat_cursor_resistance()
        self.assertEqual(self.move_cursor.call_count, calls)

    def test_pointer_escaping_in_flight_is_not_teleported_back(self):
        self.begin_jump()
        self.cursor.return_value = QPoint(999, 100)
        self.finish(N.JUMP)
        self.assertFalse(self.jump.holding)
        self.move_cursor.assert_not_called()
        self.reach(N.DIG)
        self.ai.process_chase_step()
        self.jump.dig_timer.timeout.emit()
        self.controller.on_animation_loop_finished(N.DIG.value)
        self.finish(N.END_DIG)
        self.assertTrue(self.jump.on_cooldown)

    def test_approach_near_cursor_never_teleports_to_standoff(self):
        self.cursor.return_value = QPoint(450, 550)
        self.pet.animator.force_set_node(N.STAND_IDLE)
        self.ai.start_cursor_hunt()
        self.reach(N.SNEAK)
        x = self.pet.x()
        self.ai.process_chase_step()
        self.assertLessEqual(abs(self.pet.x() - x), self.controller.ctx.cursor_hunt_speed)

    def test_already_at_standoff_exits_sneak_in_same_tick(self):
        for cursor_x in (200, 700):
            with self.subTest(cursor_x=cursor_x):
                self.controller._reset_motion_flags()
                self.pet.move(400, self.pet.ground_y)
                self.cursor.return_value = QPoint(cursor_x, 550)
                self.pet.animator.force_set_node(N.STAND_IDLE)
                self.assertTrue(self.ai.start_cursor_hunt())
                self.reach(N.SNEAK)
                target_x, _ = self.ai._get_hunt_target_x(self.cursor.return_value)
                self.pet.move(target_x, self.pet.ground_y)
                self.ai.process_chase_step()
                self.assertEqual(self.pet.x(), target_x)
                self.assertEqual(self.ai._hunt_exit_target, 'jump')
                self.assertTrue(self.ai._hunt_exit_started)
                self.assertEqual(self.pet.current_animation_node(), N.END_SNEAK)


if __name__ == '__main__':
    unittest.main()
