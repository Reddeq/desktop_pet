"""Import the supplied pixel-art pack, preserving original pixels and source files.

Run: python scripts/import_animation_pack.py E:/Assets/DesktopPet/animations_new
Requires Pillow (requirements-build.txt). No old files are deleted.
"""
import argparse
import json
from pathlib import Path
import re
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
# source directory, selected frame indices (None = all), duration, classification
CLIPS = {
    # 15 is a neutral pose; 26 duplicates 16 and would pause the loop seam.
    'sit_idle': ('Мнет хвост', list(range(1, 11)), 120, 'direct'),
    # Keep feet/body still; the adjacent Alerted2 poses only twitch the ears.
    'stand_idle': ('3. Alerted2', [2, 3, 4, 3], 240, 'reuse'),
    'walk': ('Идет Версия 2', None, 80, 'direct'),
    'stand_up': ('Встает', None, 100, 'direct'),
    'sit_down': ('Садится', None, 100, 'direct'),
    'run': ('5. Running', None, 80, 'direct'),
    'alert': ('1. Alerted', None, 100, 'direct'),
    'start_dig': ('2. Digging', list(range(5)), 90, 'direct'),
    'dig': ('2. Digging', list(range(5, 11)), 90, 'direct'),
    'end_dig': ('2. Digging', list(range(11, 16)), 90, 'direct'),
    'start_clean': ('3. Cleaning', list(range(6)), 100, 'direct'),
    'clean': ('3. Cleaning', list(range(6, 13)), 100, 'direct'),
    'end_clean': ('3. Cleaning', [13, 0], 100, 'direct'),
    'start_sandbath': ('4. Sandbathing', [0, 1, 2], 130, 'direct'),
    'sandbath': ('4. Sandbathing', list(range(3, 9)), 130, 'direct'),
    'end_sandbath': ('4. Sandbathing', list(range(9, 15)), 130, 'direct'),
    'sleep': ('2. Sleep', [4, 5, 6, 7], 180, 'direct'),
    'meow': ('4. Meowing', None, 120, 'direct'),
    'poop': ('0. Toilet', None, 100, 'direct'),
    'startle': ('0. Scared', None, 100, 'direct'),
    'start_sneak': ('1. Sneaking', [0, 1, 2], 100, 'direct'),
    'sneak': ('1. Sneaking', list(range(3, 11)), 100, 'direct'),
    'end_sneak': ('1. Sneaking', list(range(11, 17)), 100, 'direct'),
    'jump': ('Прыжок', None, 70, 'direct'),
    'start_scratch_screen': ('scratching_screen/000.png', None, 90, 'direct'),
    'scratch_screen': ('scratching_screen/001.png', None, 100, 'direct'),
    'end_scratch_screen': ('scratching_screen/002.png', None, 90, 'direct'),
    'swat': ('Точит когти', None, 80, 'placeholder'),
    'start_sharpen_claws': ('Точит когти', [0, 1], 100, 'direct'),
    'sharpen_claws': ('Точит когти', list(range(2, 9)), 90, 'direct'),
    'end_sharpen_claws': ('Точит когти', [9, 10, 0], 100, 'direct'),
    # Pass through the neighboring pose on the return to avoid a hard wrap.
    'drag': ('Прыжок', [2, 3, 4, 3], 220, 'reuse'),
    'fall': ('Прыжок', [4, 5, 6], 70, 'reuse'),
    'recover': ('Прыжок', [7, 8, 9, 10], 90, 'reuse'),
    # The supplied strip animates the head of an already lying cat. These are
    # real sleep entry/exit frames; full-body sit/lie transitions are absent.
    'lie_down': ('2. Sleep', [0, 1, 2, 3], 140, 'partial_transition'),
    'sit_up': ('2. Sleep', [8, 9], 160, 'partial_transition'),
    'yawn': ('4. Meowing', None, 160, 'placeholder'),
    'eat': ('4. Meowing', None, 120, 'reuse'),
    'start_hide': ('hiding/000.png', None, 90, 'direct'),
    'hide': ('hiding/001.png', None, 150, 'direct'),
    'end_hide': ('hiding/002.png', None, 90, 'direct'),
}
CANVAS = (112, 80)
CLIP_OFFSETS = {'drag': [(0, 0), (2, 0), (0, 0), (2, 0)]}
SHEET_SIZES = {'hiding': (64, 71), 'scratching_screen': (115, 89)}


def natural_key(path):
    return tuple((1, int(p)) if p.isdigit() else (0, p.casefold())
                 for p in re.split(r'(\d+)', path.name))


def split_sheet(path, size, allow_partial=False):
    """Split a horizontal strip. Pad the supplied truncated final hide cell."""
    width, height = size
    with Image.open(path) as image:
        if image.height != height or (image.width % width and not allow_partial):
            raise ValueError(f'Invalid sheet dimensions: {path}: {image.size}')
        image = image.convert('RGBA')
        frames = [image.crop((x, 0, x + width, height))
                  for x in range(0, image.width, width)]
    if not frames or any(frame.getbbox() is None for frame in frames):
        raise ValueError(f'Empty sheet frame: {path}')
    return frames


def bounds(frames):
    boxes = [frame.getbbox() for frame in frames]
    if any(box is None for box in boxes):
        raise ValueError('Empty frame')
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def prepare_clip(source, indices, offsets=None):
    if source.is_file():
        size = SHEET_SIZES[source.parent.name]
        partial = source.parent.name == 'hiding'
        frames = split_sheet(source, size, allow_partial=partial)
        names = [f'{source.name}#{i:03}' for i in range(len(frames))]
        if indices is not None:
            frames, names = [frames[i] for i in indices], [names[i] for i in indices]
        # One shared coordinate system for entry, loop and exit. Hiding is
        # flush with the edge; its original clipping is part of the artwork.
        if partial:
            crop = (0, 0, *size)
        else:
            group = [frame for path in sorted(source.parent.glob('*.png'))
                     for frame in split_sheet(path, size)]
            crop = bounds(group)
    else:
        files = sorted(source.glob('*.png'), key=natural_key)
        if not files:
            raise ValueError(f'No frames: {source}')
        selected = files if indices is None else [files[i] for i in indices]
        frames = []
        for path in selected:
            with Image.open(path) as image:
                frames.append(image.convert('RGBA'))
        names = [path.name for path in selected]
        if source.name == 'Прыжок':
            # The strip bakes in horizontal/vertical travel. Remove that root
            # motion for jump, fall and recovery alike; runtime owns movement.
            output = []
            for frame_index, frame in enumerate(frames):
                box = frame.getbbox()
                if box is None:
                    raise ValueError(f'Empty jump frame: {source}')
                sprite = frame.crop(box)
                if sprite.width > CANVAS[0] or sprite.height > CANVAS[1]:
                    raise ValueError(f'Jump frame exceeds canvas: {source}')
                normalized = Image.new('RGBA', CANVAS)
                dx, dy = offsets[frame_index] if offsets else (0, 0)
                normalized.paste(sprite, ((CANVAS[0] - sprite.width) // 2 + dx,
                                          CANVAS[1] - sprite.height + dy))
                output.append(normalized)
            return output, names
        if source.name in {'2. Sleep', '3. Cleaning', '2. Digging', '1. Sneaking', 'Точит когти', '4. Sandbathing'}:
            # All phases share the same origin and bounding box.
            group = []
            for path in files:
                with Image.open(path) as image:
                    group.append(image.convert('RGBA'))
            crop = bounds(group)
        else:
            crop = bounds(frames)
    # Use ONE crop for the clip, not a separate bounding box for every frame:
    # this preserves breathing, paw and body motion within the animation.
    left, top, right, bottom = crop
    width, height = right - left, bottom - top
    if width > CANVAS[0] or height > CANVAS[1]:
        raise ValueError(f'Clip exceeds canvas: {source}: {width}x{height}')
    output = []
    for frame in frames:
        normalized = Image.new('RGBA', CANVAS)
        # PIL crop pads smaller source canvases transparently (Scared has
        # variable widths). Paste without a mask to retain the original alpha.
        normalized.paste(frame.crop((left, top, right, bottom)),
                         (0 if source.parent.name == 'hiding' and source.is_file()
                          else (CANVAS[0] - width) // 2, CANVAS[1] - height))
        output.append(normalized)
    return output, names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'assets')
    args = parser.parse_args()
    # Validate/decode every clip before changing the installed pack.
    prepared = {name: prepare_clip(args.source / folder, indices, CLIP_OFFSETS.get(name))
                for name, (folder, indices, _, _) in CLIPS.items()}
    manifest = {'version': 1, 'defaults': {'pixel_art': True, 'scale': 3, 'frame_ms': 100}, 'clips': {}}
    provenance = {}
    for name, (frames, files) in prepared.items():
        folder, _, duration, kind = CLIPS[name]
        destination = args.output / 'pixel' / name
        destination.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames):
            frame.save(destination / f'{index:03}.png')
        # Remove stale generated frames only inside this exact output clip.
        expected = {f'{i:03}.png' for i in range(len(frames))}
        for path in destination.glob('*.png'):
            if path.name not in expected:
                path.unlink()
        manifest['clips'][name] = {'directory': f'pixel/{name}', 'frame_ms': duration}
        provenance[name] = {'source': folder, 'frames': files, 'kind': kind}
    (args.output / 'animations.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (args.output / 'pixel' / 'sources.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Imported {len(prepared)} clips; canvas {CANVAS}; scale 3; source unchanged')


if __name__ == '__main__':
    main()
