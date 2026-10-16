import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication
from animation_assets import AnimationAssets, AssetError
from animation_player import AnimationPlayer

APP = QApplication.instance() or QApplication([])


class AssetTests(unittest.TestCase):
    def test_loop_boundary_can_start_exit_without_advancing_its_first_frame(self):
        self.png('test/1.png')
        self.png('test/2.png')
        self.png('exit/1.png', ('green',))
        player = AnimationPlayer(str(self.root))
        self.addCleanup(player.deleteLater)
        self.addCleanup(player.timer.stop)
        loops = []
        def on_loop(name):
            loops.append(name)
            player.set_animation('exit', False)
        player.animation_loop_finished.connect(on_loop)
        player.set_animation('test', True)
        player._next_frame()
        self.assertEqual(loops, [])
        player._next_frame()
        self.assertEqual(loops, ['test'])
        self.assertEqual(player.current_animation, 'exit')
        self.assertEqual(player.current_frame_index, 0)
        self.assertTrue(player.timer.isActive())
        self.assertFalse(player._finished_emitted)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def png(self, name, colors=('red', 'blue')):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(len(colors), 1, QImage.Format.Format_ARGB32)
        for x, color in enumerate(colors):
            image.setPixelColor(x, 0, QColor(color))
        self.assertTrue(image.save(str(path), 'PNG'))

    def manifest(self, clip, defaults=None):
        (self.root / 'animations.json').write_text(json.dumps({
            'version': 1, 'defaults': defaults or {}, 'clips': {'test': clip}
        }))

    def test_natural_order_and_uppercase_png(self):
        for number, color in [(10, 'blue'), (2, 'green'), (1, 'red')]:
            self.png(f'test/frame{number}.PNG', (color,))
        clip = AnimationAssets(self.root, scale=1).load('test')
        self.assertEqual([f.toImage().pixelColor(0, 0).name() for f in clip.frames],
                         ['#ff0000', '#008000', '#0000ff'])

    def test_pixel_art_keeps_exact_colors_and_mirrors(self):
        self.png('test/1.png')
        self.manifest({'pixel_art': True, 'scale': 3})
        assets = AnimationAssets(self.root)
        image = assets.load('test').frames[0].toImage()
        self.assertEqual((image.width(), image.height()), (6, 3))
        self.assertEqual([image.pixelColor(x, 1).name() for x in range(6)],
                         ['#ff0000'] * 3 + ['#0000ff'] * 3)
        self.assertEqual(assets.load('test', False).frames[0].toImage().pixelColor(0, 0), QColor('blue'))

    def test_sheet_durations_and_count(self):
        self.png('sheet.png', ('red', 'green', 'blue'))
        self.manifest({'sheet': 'sheet.png', 'frame_size': [1, 1], 'count': 2,
                       'durations_ms': [80, 130], 'scale': 1})
        clip = AnimationAssets(self.root).load('test')
        self.assertEqual(len(clip.frames), 2)
        self.assertEqual(clip.durations_ms, (80, 130))
        self.assertEqual(clip.frames[1].toImage().pixelColor(0, 0), QColor('green'))

    def test_bad_descriptions_rejected(self):
        self.png('test/1.png')
        for options in [{'scale': 0}, {'scale': 1e308}, {'scale': float('nan')}, {'pixel_art': True, 'scale': 1.5},
                        {'frame_ms': 0}, {'durations_ms': [1, 2]}, {'directory': '../escape'},
                        {'sheet': 'test/1.png', 'frame_size': [3, 1]},
                        {'sheet': 'test/1.png', 'frame_size': [1, 1], 'count': 3},
                        {'pixel_art': 'yes'}, {'typo': 1}]:
            with self.subTest(options=options):
                self.manifest(options)
                with self.assertRaises(AssetError):
                    AnimationAssets(self.root).load('test')

    def test_corrupt_frame_does_not_silently_shorten_clip(self):
        self.png('test/1.png')
        (self.root / 'test/2.png').write_text('broken')
        with self.assertRaises(AssetError):
            AnimationAssets(self.root).load('test')

    def test_inconsistent_canvas_rejected(self):
        self.png('test/1.png', ('red',))
        self.png('test/2.png')
        with self.assertRaises(AssetError):
            AnimationAssets(self.root).load('test')

    def test_cache_avoids_redecode_and_evicts(self):
        self.png('test/1.png')
        assets = AnimationAssets(self.root, scale=1, cache_bytes=8)
        first = assets.load('test')
        with patch.object(assets, '_read', side_effect=AssertionError('decoded again')):
            self.assertIs(first, assets.load('test'))
        assets.load('test', False)
        self.assertLessEqual(assets._size, 8)
        self.assertIsNot(first, assets.load('test'))

    def test_player_finish_once_and_reentrant_next_clip(self):
        self.png('test/1.png')
        self.png('test/2.png')
        self.manifest({'durations_ms': [80, 130]})
        player = AnimationPlayer(str(self.root))
        self.addCleanup(player.deleteLater)
        self.addCleanup(player.timer.stop)
        events = []
        player.animation_finished.connect(events.append)
        self.assertTrue(player.set_animation('test', False))
        self.assertEqual(player.timer.interval(), 80)
        player._next_frame()
        self.assertEqual(player.timer.interval(), 130)
        player.set_facing_right(False)
        self.assertEqual(player.current_frame_index, 1)
        player._next_frame()
        player._next_frame()
        self.assertEqual(events, ['test'])
        self.assertFalse(player.timer.isActive())
        player.animation_finished.connect(lambda _: player.set_animation('test', True, force=True))
        player.set_animation('test', False, force=True)
        player._next_frame()
        player._next_frame()
        self.assertTrue(player.timer.isActive())
        self.assertEqual(player.current_frame_index, 0)
        self.assertFalse(player._finished_emitted)

    def test_missing_clip_stops_timer(self):
        player = AnimationPlayer(str(self.root))
        self.addCleanup(player.deleteLater)
        with self.assertLogs(level='ERROR'):
            self.assertFalse(player.set_animation('absent', False))
        self.assertFalse(player.timer.isActive())
        self.assertIn('missing directory', player.last_error)


if __name__ == '__main__':
    unittest.main()
