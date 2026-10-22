"""Synthetic desktops exercise geometry, navigation and controller integration."""
from dataclasses import replace
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from test_behaviors import APP, FakePet, N, PetController
from PyQt6.QtCore import QSettings
from pet_settings import PetSettings
from surfaces import Rect, Monitor, Window, Platform, SurfaceSnapshot, build_surfaces
from surface_navigation import NavigationConfig, SurfaceNavigator, clear_trajectory
from jump_trajectory import JumpTrajectory, flight_progress


MONITOR = Monitor('test', Rect(0, 0, 1000, 600), Rect(0, 0, 1000, 600), Rect(0, 0, 1000, 600))


class GeometryTests(unittest.TestCase):
    def test_desktop_and_window_top_use_visible_bounds(self):
        result = build_surfaces([Window(1, Rect(100, 300, 900, 550))], [MONITOR], 100, 100)
        self.assertEqual([(p.kind, p.left, p.right, p.y) for p in result.platforms],
                         [('desktop', 0, 1000, 600), ('window', 100, 900, 300)])

    def test_hidden_minimized_own_cloaked_utility_and_desktop_are_not_platforms(self):
        for flag in ('minimized', 'own', 'cloaked', 'utility', 'desktop'):
            with self.subTest(flag=flag):
                window = replace(Window(1, Rect(100, 300, 900, 500)), **{flag: True})
                self.assertEqual(len(build_surfaces([window], [MONITOR], 100, 100).platforms), 1)
        window = Window(1, Rect(100, 300, 900, 500), visible=False)
        self.assertEqual(len(build_surfaces([window], [MONITOR], 100, 100).platforms), 1)

    def test_narrow_too_high_and_maximized_edges_rejected(self):
        for rect in (Rect(100, 300, 150, 500), Rect(0, 0, 1000, 600), Rect(0, 99, 900, 500)):
            self.assertEqual(len(build_surfaces([Window(1, rect)], [MONITOR], 100, 100).platforms), 1)

    def test_z_order_splits_edge_and_reserves_headroom(self):
        back = Window(1, Rect(0, 300, 1000, 580))
        for front in (Rect(300, 250, 700, 450), Rect(300, 100, 700, 220)):
            result = build_surfaces([Window(2, front), back], [MONITOR], 100, 100)
            segments = [(p.left, p.right) for p in result.platforms if p.window == 1]
            self.assertEqual(segments, [(0, 300), (700, 1000)])
        result = build_surfaces([Window(2, back.rect), back], [MONITOR], 100, 100)
        self.assertFalse(any(p.window == 1 for p in result.platforms))

    def test_window_behind_cannot_occlude_front_platform(self):
        result = build_surfaces([Window(1, Rect(100, 300, 900, 500)),
                                 Window(2, Rect(0, 0, 1000, 600))], [MONITOR], 100, 100)
        self.assertTrue(any(p.window == 1 for p in result.platforms))

    def test_utility_window_occludes_but_does_not_offer_a_surface(self):
        result = build_surfaces([Window(2, Rect(0, 250, 1000, 350), utility=True),
                                 Window(1, Rect(0, 300, 1000, 550))], [MONITOR], 100, 100)
        self.assertEqual(len(result.platforms), 1)

    def test_dpi_conversion_is_local_to_negative_monitor_origin(self):
        monitor = Monitor('left', Rect(-2560, -200, 0, 1240), Rect(-2560, -200, -1280, 520),
                          Rect(-2560, -200, -1280, 500), 2)
        self.assertEqual(monitor.to_logical(Rect(-2360, 400, -560, 1000)),
                         Rect(-2460, 100, -1560, 400))
        result = build_surfaces([Window(1, Rect(-2360, 400, -560, 1000))], [monitor], 100, 100)
        self.assertEqual(result.platforms[1].y, 100)

    def test_spanning_window_has_separate_segments_on_each_monitor(self):
        other = Monitor('left', Rect(-1000, 0, 0, 600), Rect(-1000, 0, 0, 600), Rect(-1000, 0, 0, 600))
        result = build_surfaces([Window(1, Rect(-600, 300, 500, 550))], [MONITOR, other], 100, 100)
        self.assertEqual({(p.monitor, p.left, p.right) for p in result.platforms if p.window},
                         {('left', -600, 0), ('test', 0, 500)})

    def test_fullscreen_only_suppresses_its_monitor_when_foreground(self):
        window = Window(1, MONITOR.native)
        self.assertEqual(build_surfaces([window], [MONITOR], 100, 100, 1).fullscreen, {'test'})
        self.assertFalse(build_surfaces([window], [MONITOR], 100, 100, 2).fullscreen)

    def test_background_window_is_not_a_wall_in_front_of_the_supporting_window(self):
        front = Window(1, Rect(200, 350, 800, 550))
        background = Window(2, Rect(0, 0, 1000, 600))
        snapshot = build_surfaces([front, background], [MONITOR], 100, 100)
        self.assertEqual(snapshot.blockers('test', source_window=1), [front.rect])
        self.assertEqual(snapshot.blockers('test', target_window=1), [front.rect])


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.nav = SurfaceNavigator(NavigationConfig(max_distance=180, max_rise=150))
        self.a = Platform('a', 'window', 0, 180, 800, 'test')
        self.b = Platform('b', 'window', 200, 380, 700, 'test')
        self.c = Platform('c', 'window', 400, 580, 600, 'test')

    def test_route_can_require_multiple_jumps_and_cache_invalidates_on_geometry(self):
        snapshot = SurfaceSnapshot((self.a, self.b, self.c), ())
        route = self.nav.route(snapshot, 'a', 'c', 50, 60)
        self.assertEqual([step.target for step in route], ['b', 'c'])
        self.assertIs(self.nav.graph(snapshot, 50, 60), self.nav.graph(snapshot, 50, 60))
        changed = replace(snapshot, platforms=(self.a, replace(self.b, y=100), self.c))
        self.assertFalse(self.nav.route(changed, 'a', 'c', 50, 60))

    def test_distance_height_width_and_other_monitor_limit_jumps(self):
        for target in (replace(self.b, left=900, right=1100), replace(self.b, y=100),
                       replace(self.b, right=240), replace(self.b, monitor='other')):
            self.assertIsNone(self.nav.plan(self.a, target, 50, 60, []))

    def test_descent_has_no_height_limit_but_ascent_remains_limited(self):
        target = replace(self.b, y=3500)
        plan = self.nav.plan(self.a, target, 50, 60, [], Rect(0, 0, 1000, 4000))
        self.assertIsNotNone(plan)
        self.assertEqual(plan.trajectory.end_y - plan.trajectory.start_y, 2700)
        self.assertIsNone(self.nav.plan(target, self.a, 50, 60, []))

    def test_descent_from_ceiling_needs_no_upward_headroom_at_any_height(self):
        source = replace(self.a, y=60)
        target = replace(self.b, y=4000)
        plan = self.nav.plan(source, target, 50, 60, [], Rect(0, 0, 1000, 5000))
        self.assertIsNotNone(plan)
        self.assertGreater(plan.trajectory.position(.1)[1], source.y)

    def test_points_fit_surfaces_and_trajectory_has_smooth_landing(self):
        plan = self.nav.plan(self.a, self.b, 50, 60, [])
        self.assertTrue(self.a.fits(plan.launch_x, 50))
        self.assertTrue(self.b.fits(plan.landing_x, 50))
        self.assertEqual(plan.trajectory.position(0), (plan.launch_x, self.a.y))
        self.assertEqual(plan.trajectory.position(1), (plan.landing_x, self.b.y))
        self.assertLess(plan.trajectory.position(.5)[1], min(self.a.y, self.b.y))
        self.assertEqual(flight_progress(1 / 11), 0)
        self.assertEqual(flight_progress(8 / 11), 1)

    def test_obstacles_and_screen_ceiling_block_a_jump(self):
        obstacle = Rect(180, 0, 200, 900)
        self.assertIsNone(self.nav.plan(self.a, self.b, 50, 60, [obstacle]))
        self.assertIsNone(self.nav.plan(self.a, self.b, 50, 60, [], Rect(0, 700, 1000, 1000)))

    def test_cannot_drop_through_source_window(self):
        source = Platform('high', 'window', 100, 400, 300, 'test')
        floor = Platform('floor', 'desktop', 0, 1000, 900, 'test')
        plan = self.nav.plan(source, floor, 50, 60, [Rect(100, 300, 400, 800)])
        if plan is not None:
            self.assertTrue(clear_trajectory(plan.trajectory, [Rect(100, 300, 400, 800)], 50, 60))
        self.assertFalse(clear_trajectory(JumpTrajectory(200, 300, 200, 900, 200),
                                          [Rect(100, 300, 400, 800)], 50, 60))


class Tracker:
    def __init__(self):
        self.windows = [Window(1, Rect(200, 350, 800, 550))]
        self.foreground = None
        self.dirty = threading.Event()
        self.started = False
        self.scans = 0

    def start(self): self.started = True
    def close(self): self.started = False
    def scan(self):
        self.scans += 1
        return self.windows, self.foreground
    def window(self, handle): return next((w for w in self.windows if w.handle == handle), None)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.pet = FakePet()
        self.controller = PetController(self.pet, plugin_dirs=[])
        self.surfaces = self.controller.surfaces
        self.tracker = Tracker()
        self.surfaces.tracker = self.tracker
        self.surfaces._monitors = lambda: (MONITOR,)
        self.now = 1000
        self.surfaces.clock = lambda: self.now
        self.surfaces.set_enabled(True)

    def tearDown(self):
        self.controller.stop()
        self.controller.deleteLater()
        APP.processEvents()

    def attach(self):
        window = next(p for p in self.surfaces.snapshot.platforms if p.window == 1)
        self.pet.move(300, 250)
        self.surfaces.attach(window)
        return window

    def test_default_is_off_and_does_not_allocate_native_resources(self):
        other = PetController(FakePet(), plugin_dirs=[])
        try:
            self.assertFalse(other.surfaces.enabled)
            self.assertIsNone(other.surfaces.tracker)
            self.assertFalse(other.surfaces.tick())
        finally:
            other.stop()
            other.deleteLater()

    def test_attached_pet_follows_window_without_restarting_animation(self):
        self.attach()
        self.controller.behaviors.start('clean')
        scenario = self.controller.behaviors.active
        node = self.pet.current_animation_node()
        self.tracker.windows = [Window(1, Rect(250, 370, 850, 570))]
        self.surfaces.tick()
        self.assertEqual((self.pet.x(), self.pet.y(), self.pet.ground_y), (350, 270, 270))
        self.assertIs(self.controller.behaviors.active, scenario)
        self.assertEqual(self.pet.current_animation_node(), node)

    def test_window_follow_does_not_move_walk_goal_by_the_pets_own_steps(self):
        self.attach()
        self.controller.ctx.is_walk = True
        self.controller.ctx.walk_target_x = 500
        self.pet.move(304, 250)
        self.surfaces._follow()
        self.assertEqual(self.controller.ctx.walk_target_x, 500)
        self.tracker.windows = [Window(1, Rect(230, 350, 830, 550))]
        self.surfaces._follow()
        self.assertEqual(self.pet.x(), 334)
        self.assertEqual(self.controller.ctx.walk_target_x, 530)

    def test_disappearance_or_occlusion_causes_existing_gravity_and_recovery(self):
        for occlusion in (False, True):
            self.tracker.windows = [Window(1, Rect(200, 350, 800, 550))]
            self.surfaces.refresh()
            self.attach()
            y = self.pet.y()
            self.tracker.windows = ([Window(2, Rect(0, 200, 1000, 450)), *self.tracker.windows]
                                    if occlusion else [])
            self.surfaces.refresh()
            self.assertTrue(self.controller.ctx.is_fall)
            self.assertEqual(self.pet.y(), y)
            for _ in range(100):
                self.controller.motion.apply_gravity()
            self.assertEqual(self.pet.y(), 500)
            self.assertTrue(self.controller.ctx.is_recover)
            self.assertEqual(self.surfaces.current.kind, 'desktop')
            self.controller.ctx.is_recover = False

    def test_resize_too_small_drops_instead_of_teleporting(self):
        self.attach()
        self.tracker.windows = [Window(1, Rect(200, 350, 250, 550))]
        self.surfaces.tick()
        self.assertTrue(self.controller.ctx.is_fall)
        self.assertEqual(self.pet.y(), 250)

    def test_fast_disappearance_never_lands_back_on_stale_snapshot(self):
        self.attach()
        self.tracker.windows = []
        self.surfaces.tick()
        self.assertTrue(self.controller.ctx.is_fall)
        self.assertEqual(self.pet.ground_y, 500)
        self.controller.motion.apply_gravity()
        self.assertGreater(self.pet.y(), 250)

    def test_fractional_dpi_attachment_uses_absolute_origin_without_drift(self):
        monitor = replace(MONITOR, native=Rect(0, 0, 1500, 900), scale=1.5)
        self.surfaces._monitors = lambda: (monitor,)
        self.tracker.windows = [Window(1, Rect(300, 525, 1200, 825))]
        self.surfaces.refresh()
        self.attach()
        x = self.pet.x()
        for delta in list(range(1, 40)) + list(range(38, -1, -1)):
            self.tracker.windows = [Window(1, Rect(300 + delta, 525, 1200 + delta, 825))]
            self.surfaces._follow()
            if delta % 3 == 0:
                self.surfaces.refresh()
            self.assertEqual(self.pet.x(), round(x + delta / 1.5))
        self.assertEqual(self.pet.x(), x)

    def test_disable_on_window_returns_by_gravity_and_releases_hooks(self):
        self.attach()
        self.surfaces.set_enabled(False)
        self.assertFalse(self.tracker.started)
        self.assertTrue(self.controller.ctx.is_fall)
        self.assertEqual(self.pet.y(), 250)
        self.assertEqual(self.pet.ground_y, 500)

    def test_drop_lands_on_nearest_platform_below_feet(self):
        self.pet.move(300, 100)
        self.surfaces.prepare_drop()
        self.assertEqual(self.pet.ground_y, 250)
        self.controller.start_fall()
        for _ in range(100):
            self.controller.motion.apply_gravity()
        self.assertEqual(self.pet.y(), 250)
        self.assertTrue(self.surfaces.on_window)

    def test_release_exactly_on_window_attaches_without_airborne_frame(self):
        from PyQt6.QtCore import QPointF
        self.controller.on_mouse_press(QPointF(300, 250))
        self.pet.move(300, 250)
        self.controller.on_mouse_release()
        self.assertTrue(self.surfaces.on_window)
        self.assertFalse(self.controller.ctx.is_fall)

    def test_disconnected_monitor_uses_emergency_visible_position(self):
        self.attach()
        self.pet.move(-1200, 250)
        self.surfaces._monitors = lambda: ()
        self.surfaces.refresh()
        self.assertTrue(self.controller.ctx.is_fall)
        self.assertGreaterEqual(self.pet.x(), 0)
        self.assertLessEqual(self.pet.x() + self.pet.width(), 1000)

    def test_desktop_only_scenarios_defer_while_clean_and_sleep_work(self):
        self.attach()
        with patch('surface_controller.random.random', return_value=.99):
            for name in ('hide', 'sharpen_claws', 'poop', 'inspect_notifications', 'enter'):
                self.assertFalse(self.controller.behaviors.start(name), name)
        for name in ('clean', 'sleep', 'sandbath', 'eat', 'walk'):
            self.assertTrue(self.controller.behaviors.start(name), name)

    def test_no_full_enumeration_on_every_animation_or_movement_tick(self):
        self.attach()
        count = self.tracker.scans
        for _ in range(100):
            self.surfaces.tick()
        self.assertEqual(self.tracker.scans, count)
        self.now += 1.1
        self.surfaces.tick()
        self.assertEqual(self.tracker.scans, count + 1)

    def test_jump_then_land_and_cancel_if_target_disappears(self):
        for disappear in (False, True):
            self.controller.ctx.is_fall = False
            self.surfaces.current = None
            self.tracker.windows = [Window(1, Rect(200, 350, 800, 550))]
            self.surfaces.refresh()
            self.pet.move(0, 500)
            source, target = self.surfaces.snapshot.platforms
            plan = self.surfaces.navigator.plan(source, target, 100, 100,
                                               [self.tracker.windows[0].rect], MONITOR.work)
            self.assertIsNotNone(plan)
            self.pet.move(round(plan.launch_x), 500)
            self.surfaces.travel.begin(plan)
            self.pet.force_set_animation_node(N.WALK)
            self.surfaces.tick()
            self.assertEqual(self.surfaces.travel.phase, 'jump')
            self.now += .35
            self.surfaces.tick()
            airborne_y = self.pet.y()
            self.assertLess(airborne_y, 500)
            if disappear:
                self.tracker.windows = []
                self.surfaces.refresh()
                self.assertFalse(self.surfaces.travel.active)
                self.assertTrue(self.controller.ctx.is_fall)
                self.assertEqual(self.pet.y(), airborne_y)
            else:
                self.controller.on_animation_finished(N.JUMP.value)
                self.now += .5
                self.surfaces.tick()
                self.assertFalse(self.surfaces.travel.active)
                self.assertTrue(self.surfaces.on_window)
                self.assertEqual(self.pet.y(), 250)


class SettingsTests(unittest.TestCase):
    def test_default_off_and_saved_setting_survives_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'settings.ini')
            settings = PetSettings(QSettings(path, QSettings.Format.IniFormat))
            self.assertFalse(settings.walk_on_windows)
            settings.walk_on_windows = True
            other = PetSettings(QSettings(path, QSettings.Format.IniFormat))
            self.assertTrue(other.walk_on_windows)
            other.walk_on_windows = False
            self.assertFalse(PetSettings(QSettings(path, QSettings.Format.IniFormat)).walk_on_windows)
