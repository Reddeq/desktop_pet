import importlib.util
from pathlib import Path
import tempfile
import unittest
from PIL import Image

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts/import_animation_pack.py'
spec = importlib.util.spec_from_file_location('pack_importer', SCRIPT)
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


class PackImportTests(unittest.TestCase):
    def test_jump_removes_baked_root_motion_without_changing_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'Прыжок'
            folder.mkdir()
            for index, (x, y) in enumerate([(2, 20), (40, 3)]):
                image = Image.new('RGBA', (100, 50))
                image.putpixel((x, y), (255, 40, 20, 128))
                image.save(folder / f'{index}.png')
            frames, _ = pack.prepare_clip(folder, None)
            self.assertEqual(frames[0].tobytes(), frames[1].tobytes())
            self.assertEqual(frames[0].getpixel(frames[0].getbbox()[:2]), (255, 40, 20, 128))

    def test_sleep_phases_share_coordinates_across_selected_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / '2. Sleep'
            folder.mkdir()
            for index, (x, y) in enumerate([(3, 1), (3, 4), (5, 1)]):
                image = Image.new('RGBA', (8, 6))
                image.putpixel((x, y), (255, 40, 20, 255))
                image.save(folder / f'{index:03}.png')
            entry, _ = pack.prepare_clip(folder, [0])
            loop, _ = pack.prepare_clip(folder, [1])
            exit_frames, _ = pack.prepare_clip(folder, [2])
            self.assertEqual(loop[0].getbbox()[1] - entry[0].getbbox()[1], 3)
            self.assertEqual(exit_frames[0].getbbox()[0] - entry[0].getbbox()[0], 2)

    def test_fall_and_recovery_use_same_normalization_as_jump(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'Прыжок'
            folder.mkdir()
            for index in range(11):
                frame = Image.new('RGBA', (100, 70))
                frame.paste((30 + index, 60, 90, 255), (index * 4, index, index * 4 + 5, index + 8))
                frame.save(folder / f'{index + 1}.png')
            jump, _ = pack.prepare_clip(folder, None)
            for name in ('fall', 'recover'):
                _, indices, _, _ = pack.CLIPS[name]
                frames, _ = pack.prepare_clip(folder, indices)
                for frame, index in zip(frames, indices):
                    self.assertEqual(frame.tobytes(), jump[index].tobytes())
            drag, _ = pack.prepare_clip(folder, pack.CLIPS['drag'][1], pack.CLIP_OFFSETS['drag'])
            self.assertEqual(len(drag), 4)
            expected = Image.new('RGBA', pack.CANVAS)
            expected.paste(jump[3], (2, 0))
            self.assertEqual(drag[1].tobytes(), expected.tobytes())

    def test_sandbath_phases_keep_original_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / '4. Sandbathing'
            folder.mkdir()
            for index in range(15):
                image = Image.new('RGBA', (32, 32))
                image.paste((index, 80, 100, 255), (index, index % 3, index + 5, index % 3 + 5))
                image.save(folder / f'{index:03}.png')
            whole, names = pack.prepare_clip(folder, None)
            combined, combined_names = [], []
            for name in ('start_sandbath', 'sandbath', 'end_sandbath'):
                frames, files = pack.prepare_clip(folder, pack.CLIPS[name][1])
                combined.extend(frames)
                combined_names.extend(files)
            self.assertEqual(combined_names, names)
            self.assertEqual([f.tobytes() for f in combined], [f.tobytes() for f in whole])

    def test_sheet_split_pads_partial_last_cell_without_losing_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sheet.png'
            image = Image.new('RGBA', (6, 3))
            image.putpixel((0, 2), (1, 2, 3, 128))
            image.putpixel((5, 2), (4, 5, 6, 255))
            image.save(path)
            frames = pack.split_sheet(path, (4, 3), allow_partial=True)
            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[1].size, (4, 3))
            self.assertEqual(frames[0].getpixel((0, 2)), (1, 2, 3, 128))
            self.assertEqual(frames[1].getpixel((1, 2)), (4, 5, 6, 255))
            self.assertEqual(frames[1].getpixel((3, 2))[3], 0)
            with self.assertRaises(ValueError):
                pack.split_sheet(path, (4, 3))

    def test_sheet_phases_share_origin_and_keep_hide_flush_with_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'hiding'
            folder.mkdir()
            for index, x in enumerate([0, 20, 40]):
                image = Image.new('RGBA', (64, 71))
                image.putpixel((x, 70), (255, 40, 20, 255))
                image.save(folder / f'{index:03}.png')
            for index, x in enumerate([0, 20, 40]):
                frames, names = pack.prepare_clip(folder / f'{index:03}.png', None)
                self.assertEqual(frames[0].getbbox(), (x, 79, x + 1, 80))
                self.assertEqual(names, [f'{index:03}.png#000'])

    def test_scratch_does_not_crop_phases_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'scratching_screen'
            folder.mkdir()
            for index, y in enumerate([88, 15, 80]):
                image = Image.new('RGBA', (115, 89))
                image.putpixel((30, y), (255, 40, 20, 255))
                image.save(folder / f'{index:03}.png')
            entry, _ = pack.prepare_clip(folder / '000.png', None)
            loop, _ = pack.prepare_clip(folder / '001.png', None)
            self.assertEqual(entry[0].getbbox()[1] - loop[0].getbbox()[1], 73)
            self.assertEqual(entry[0].getbbox()[0], loop[0].getbbox()[0])

    def test_variable_canvas_preserves_pixels_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, width, x in [('2.png', 5, 2), ('10.png', 7, 4)]:
                frame = Image.new('RGBA', (width, 4))
                frame.putpixel((x, 3), (255, 40, 20, 128))
                frame.save(folder / name)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            frames, files = pack.prepare_clip(folder, None)
            self.assertEqual(files, ['2.png', '10.png'])
            self.assertTrue(all(f.size == pack.CANVAS for f in frames))
            self.assertEqual(frames[1].getbbox()[0] - frames[0].getbbox()[0], 2)
            self.assertEqual(frames[0].getpixel(frames[0].getbbox()[:2]), (255, 40, 20, 128))
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_selected_frames_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for index in range(3):
                Image.new('RGBA', (4, 4), (index, 0, 0, 255)).save(folder / f'{index}.png')
            frames, files = pack.prepare_clip(folder, [2, 0])
            self.assertEqual(files, ['2.png', '0.png'])
            self.assertEqual(len(frames), 2)

    def test_pack_covers_all_graph_nodes(self):
        import sys
        sys.path.insert(0, str(SCRIPT.parent.parent / 'src'))
        from animation_node import AnimationNode
        self.assertEqual(set(pack.CLIPS), {node.value for node in AnimationNode})


if __name__ == '__main__':
    unittest.main()
