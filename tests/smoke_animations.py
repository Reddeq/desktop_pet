"""Exercise installed sprite phases with the real offscreen Qt playback clock."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PyQt6.QtCore import QElapsedTimer, QPoint, QPointF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from animation_node import AnimationNode as N
from app import FrameAnimatedPet


def wait_until(predicate, label, timeout=5000):
    clock = QElapsedTimer()
    clock.start()
    while not predicate() and clock.elapsed() < timeout:
        QTest.qWait(20)
    assert predicate(), f"Playback timed out: {label}"


def fire_phase_timer(scenario):
    assert len(scenario._timers) == 1
    timer = next(iter(scenario._timers))
    timer.stop()
    timer.timeout.emit()


def main():
    app = QApplication.instance() or QApplication([])
    pet = FrameAnimatedPet()
    assert pet.controller.behaviors.active.id == 'enter'
    assert pet.current_animation_node() == N.RUN
    assert not pet.geometry().intersects(pet.get_current_screen_rect())
    pet.controller.stop()  # Keep cursor interaction and autonomous ticks off.
    pet.debug_console.stop()
    manager = pet.controller.behaviors
    try:
        pet.animator.force_set_node(N.STAND_IDLE)
        assert len(pet.animation_player.frames) == 4
        assert pet.animation_player.current_loop
        idle_frames = []
        def record_stand_idle(_):
            idle_frames.append(pet.current_animation_node())
        pet.animation_player.frame_changed.connect(record_stand_idle)
        wait_until(lambda: len(idle_frames) >= 8, 'two calm standing loops')
        pet.animation_player.frame_changed.disconnect(record_stand_idle)
        assert set(idle_frames) == {N.STAND_IDLE}
        pet.animator.force_set_node(N.RUN)
        assert manager.start("hide")
        scenario = manager.active
        exit_widths = []
        for _ in range(2000):
            exit_widths.append(pet.geometry().intersected(pet.get_current_screen_rect()).width())
            pet.controller.process_walk_step()
            if scenario.phase == 'hidden':
                break
        assert scenario.phase == 'hidden'
        assert any(0 < width < pet.width() for width in exit_widths)
        assert not pet.geometry().intersects(pet.get_current_screen_rect())
        assert not pet.isVisible()
        fire_phase_timer(scenario)
        assert pet.current_animation_node() == N.START_HIDE
        wait_until(lambda: scenario.phase == "hide", "hide entry")
        assert pet.current_animation_node() == N.HIDE
        fire_phase_timer(scenario)
        wait_until(lambda: scenario.phase == "return", "hide exit")
        assert not pet.isVisible()
        fire_phase_timer(scenario)
        assert scenario.phase == 'enter'
        assert not pet.geometry().intersects(pet.get_current_screen_rect())
        widths = []
        while manager.active is scenario:
            widths.append(pet.geometry().intersected(pet.get_current_screen_rect()).width())
            pet.controller.process_walk_step()
        assert any(0 < width < pet.width() for width in widths)
        assert pet._screen_clip is None
        assert pet.label.clip_rect is None
        assert pet.isVisible() and pet.y() == pet.ground_y
        pet.move(pet.x(), pet.ground_y - 150)
        pet.controller.on_mouse_press(QPointF(pet.x(), pet.y()))
        assert len(pet.animation_player.frames) == 4
        fall_nodes = []
        def record_fall(_):
            fall_nodes.append(pet.current_animation_node())
        pet.animation_player.frame_changed.connect(record_fall)
        wait_until(lambda: len(fall_nodes) >= 8, "calm drag loops")
        pet.animation_player.frame_changed.disconnect(record_fall)
        assert set(fall_nodes) == {N.DRAG}
        pet.controller.on_mouse_release()
        assert pet.current_animation_node() == N.FALL
        assert len(pet.animation_player.frames) == 3
        assert not pet.animation_player.current_loop
        wait_until(lambda: pet.animation_player._finished_emitted, "airborne jump continuation")
        assert pet.current_animation_node() == N.FALL
        assert pet.controller.ctx.is_fall
        pet.controller.motion._land()
        assert pet.current_animation_node() == N.RECOVER
        assert len(pet.animation_player.frames) == 4
        assert not pet.animation_player.current_loop
        wait_until(lambda: not pet.controller.ctx.is_recover, "four-frame landing")
        assert pet.y() == pet.ground_y
        assert manager.start('sharpen_claws')
        scenario = manager.active
        wait_until(lambda: pet.current_animation_node() == N.RUN, 'run to sharpen claws')
        for _ in range(2000):
            pet.controller.process_walk_step()
            if scenario.phase == 'start':
                break
        assert scenario.phase == 'start'
        wait_until(lambda: pet.current_animation_node() == N.SHARPEN_CLAWS, 'claw raise')
        assert len(pet.animation_player.frames) == 7
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        wait_until(lambda: scenario.phase == 'end', 'claw cycle boundary')
        assert pet.current_animation_node() == N.END_SHARPEN_CLAWS
        wait_until(lambda: scenario.phase == 'return', 'claw lower')
        wait_until(lambda: pet.current_animation_node() == N.RUN, 'step back from edge')
        for _ in range(500):
            pet.controller.process_walk_step()
            if manager.active is None:
                break
        assert manager.active is None
        assert pet.label.clip_rect is None
        assert not pet.controller.cursor_ai.cursor_resist_timer.isActive()
        assert manager.start('sandbath')
        scenario = manager.active
        wait_until(lambda: pet.current_animation_node() == N.START_SANDBATH, 'sandbath lay down')
        assert not scenario._timers
        wait_until(lambda: pet.current_animation_node() == N.SANDBATH, 'sandbath entry')
        assert len(pet.animation_player.frames) == 6
        assert pet.animation_player.current_loop
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        assert pet.current_animation_node() == N.SANDBATH
        wait_until(lambda: scenario.phase == 'end', 'sandbath complete roll')
        assert pet.current_animation_node() == N.END_SANDBATH
        wait_until(lambda: manager.active is None, 'sandbath roll and rise')
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, 'sandbath idle')
        assert manager.start("beg_food")
        wait_until(lambda: pet.current_animation_node() == N.SCRATCH_SCREEN,
                   "scratch entry")
        manager.active.finish()
        assert pet.current_animation_node() == N.END_SCRATCH_SCREEN
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE,
                   "scratch exit and sit down")
        ai = pet.controller.cursor_ai
        food_position = QPoint(pet.x() + pet.width() // 2, pet.y() + pet.height() // 2)
        with patch.object(ai, '_feed_mode_active', return_value=True) as mode, patch(
            'pet_cursor_ai.QCursor.pos', return_value=food_position
        ):
            ai.check_cursor_proximity()
            scenario = manager.active
            assert scenario.id == 'food_beg'
            wait_until(lambda: pet.current_animation_node() == N.SCRATCH_SCREEN, 'food beg entry')
            food_loops = []
            def record_food_loop(node):
                if node == N.SCRATCH_SCREEN.value:
                    food_loops.append(node)
            pet.animation_player.animation_loop_finished.connect(record_food_loop)
            wait_until(lambda: len(food_loops) >= 2, 'persistent food beg loops')
            pet.animation_player.animation_loop_finished.disconnect(record_food_loop)
            ai.check_cursor_proximity()
            assert manager.active is scenario and not scenario._timers
            mode.return_value = False
            pet.controller.process_walk_step()
            assert manager.active is None
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, 'food beg exit')
        assert manager.start("sleep")
        scenario = manager.active
        wait_until(lambda: pet.current_animation_node() == N.SLEEP, "sleep entry")
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        assert manager.active is scenario  # Wake waits for the breathing cycle.
        wait_until(lambda: manager.active is None, "sleep cycle boundary")
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, "sleep exit")
        assert manager.start("clean")
        scenario = manager.active
        assert pet.current_animation_node() == N.START_CLEAN
        wait_until(lambda: pet.current_animation_node() == N.CLEAN, "raise paw")
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        assert scenario.phase == "clean"
        wait_until(lambda: scenario.phase == "end", "washing cycle boundary")
        assert manager.active is scenario
        wait_until(lambda: manager.active is None, "lower paw")
        assert pet.current_animation_node() == N.SIT_IDLE
        assert pet.controller.try_feed()
        scenario = manager.active
        wait_until(lambda: pet.current_animation_node() == N.EAT, "chew using meow frames")
        assert len(pet.animation_player.frames) == 5
        assert pet.animation_player.current_loop
        pet.controller.process_walk_step()
        eat_clock = QElapsedTimer()
        eat_clock.start()
        wait_until(lambda: pet.current_animation_node() == N.CLEAN, "clean after five-second eating loop", 8000)
        assert 4900 <= eat_clock.elapsed() <= 7500, eat_clock.elapsed()
        assert manager.active is scenario
        assert not pet.controller.try_feed()
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        wait_until(lambda: manager.active is None, "finish cleaning after eating")
        assert not pet.controller.try_feed()
        assert pet.controller.food_cooldown_until > manager._clock() + 59
        ai = pet.controller.cursor_ai
        loops = []
        record_loop = loops.append
        pet.animation_player.animation_loop_finished.connect(record_loop)
        with patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(
            pet.x() + pet.width() - 20, pet.y() + int(pet.height() * .7)
        )), patch('pet_cursor_ai.QCursor.setPos'):
            ai.start_cursor_swat()
            wait_until(lambda: pet.current_animation_node() == N.SWAT, "single swat entry")
            assert not pet.animation_player.current_loop
            wait_until(lambda: not pet.controller.ctx.is_swat_cursor, "single swat completion")
            assert not ai.cursor_resist_timer.isActive()
        assert N.SWAT.value not in loops
        pet.animation_player.animation_loop_finished.disconnect(record_loop)
        ai.post_swat_caution_timer.stop()
        ai.finish_post_swat_caution()
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, "swat idle")
        with patch('pet_cursor_ai.QCursor.pos', return_value=QPoint(
            pet.x() + int(pet.width() * .3), pet.y() + int(pet.height() * .6)
        )), patch('pet_cursor_ai.QCursor.setPos') as move_cursor:
            ai.start_rear_startle_swat(QPoint(pet.x(), pet.y()))
            wait_until(lambda: pet.current_animation_node() == N.SWAT, "startle to swat")
            step = pet.animator.current_step
            pet.controller.process_walk_step()
            assert pet.animator.current_step is step
            assert ai.cursor_resist_timer.isActive()
            wait_until(lambda: not pet.controller.ctx.is_swat_cursor, "startle swat releases")
            assert move_cursor.called
            assert not ai.cursor_resist_timer.isActive()
        ai.post_swat_caution_timer.stop()
        ai.finish_post_swat_caution()
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, "startle swat idle")
        assert manager.start("inspect_notifications")
        scenario = manager.active
        wait_until(lambda: scenario.phase == "run", "notification alert")
        wait_until(lambda: pet.current_animation_node() == N.RUN, "notification run")
        pet.controller.motion.stop_horizontal_motion()
        pet.controller.process_walk_step()
        wait_until(lambda: pet.current_animation_node() == N.DIG, "dig entry")
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        assert scenario.phase == "dig"
        wait_until(lambda: scenario.phase == "dig_end", "dig cycle boundary")
        assert manager.active is scenario
        wait_until(lambda: manager.active is None, "dig exit")
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, "dig idle")
        ai = pet.controller.cursor_ai
        hunt_target = QPoint(pet.get_current_screen_rect().center().x(), pet.get_current_screen_rect().bottom() - 20)
        with patch('cursor_jump.QCursor.pos', return_value=hunt_target):
            assert ai.start_cursor_hunt()
        wait_until(lambda: pet.current_animation_node() == N.SNEAK, "sneak entry")
        assert len(pet.animation_player.frames) == 8
        seen = []
        def record_sneak_frame(_):
            seen.append(pet.current_animation_node())
        pet.animation_player.frame_changed.connect(record_sneak_frame)
        wait_until(lambda: len(seen) >= 16, "two uninterrupted sneak loops")
        pet.animation_player.frame_changed.disconnect(record_sneak_frame)
        assert set(seen) == {N.SNEAK}, seen
        ai.finish_cursor_hunt()
        wait_until(lambda: pet.current_animation_node() == N.END_SNEAK, "sneak loop boundary")
        assert pet.controller.ctx.is_hunt_cursor
        wait_until(lambda: not pet.controller.ctx.is_hunt_cursor, "sneak exit")
        wait_until(lambda: pet.current_animation_node() == N.SIT_IDLE, "sneak idle")
        screen = pet.get_current_screen_rect()
        target = QPoint(screen.center().x(), screen.bottom() - 20)
        mouse = [target]
        ai._hunt_retry_until = 0.0  # This independent playback case starts after the abort pause.
        with patch('cursor_jump.QCursor.pos', side_effect=lambda: mouse[0]), patch(
            'cursor_jump.QCursor.setPos', side_effect=lambda x, y: mouse.__setitem__(0, QPoint(x, y))
        ) as capture:
            assert ai.start_cursor_hunt()
            # Only movement is enabled: cursor polling and autonomy stay off.
            pet.controller.walk_timer.start()
            wait_until(lambda: ai.jump.phase == 'jump', 'cursor jump')
            wait_until(lambda: pet.y() < pet.ground_y, 'jump arc')
            wait_until(lambda: ai.jump.phase == 'dig', 'capture and dig')
            assert capture.called
            assert all(screen.contains(QPoint(*call.args)) for call in capture.call_args_list)
            assert pet.y() == pet.ground_y
            assert ai.jump.holding
            ai.jump.release_timer.timeout.emit()
            assert not ai.jump.holding
            ai.jump.dig_timer.timeout.emit()
            wait_until(lambda: not ai.jump.active, 'hunt dig exit')
            assert ai.jump.on_cooldown
            assert not ai.cursor_resist_timer.isActive()
            pet.controller.walk_timer.stop()
        assert manager.start('poop')
        scenario = manager.active
        wait_until(lambda: pet.current_animation_node() == N.RUN, 'poop run')
        pet.controller.motion.stop_horizontal_motion()
        pet.controller.process_walk_step()
        wait_until(lambda: pet.current_animation_node() == N.START_POOP, 'poop squat')
        assert len(pet.animation_player.frames) == 6
        wait_until(lambda: pet.current_animation_node() == N.POOP, 'poop seated loop')
        assert len(pet.animation_player.frames) == 18
        assert pet.animation_player.current_loop
        pet.controller.process_walk_step()
        clock = QElapsedTimer()
        clock.start()
        wait_until(lambda: pet.current_animation_node() == N.END_POOP, 'five-second poop loop', 7000)
        assert 4900 <= clock.elapsed() <= 6500, clock.elapsed()
        assert len(pet.animation_player.frames) == 4
        wait_until(lambda: pet.current_animation_node() == N.DIG, 'poop dig entry')
        pet.controller.process_walk_step()
        fire_phase_timer(scenario)
        wait_until(lambda: manager.active is not scenario, 'poop dig exit')
        assert manager.active.id == 'run'
        assert not manager.errors, manager.errors
        print("Qt playback: all phases plus cursor jump/capture/dig/cooldown OK; mouse mocked")
    finally:
        pet.controller.stop()
        pet.close()


if __name__ == "__main__":
    main()
