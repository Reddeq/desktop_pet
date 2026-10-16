"""Validate animation assets without opening the pet window."""
import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from PyQt6.QtWidgets import QApplication
from animation_assets import AnimationAssets, AssetError
from animation_node import AnimationNode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('assets', nargs='?', type=Path, default=Path(__file__).resolve().parent.parent / 'assets')
    parser.add_argument('--strict', action='store_true', help='Require optional yawn clip too')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    try:
        assets = AnimationAssets(args.assets, scale=0.3)
    except (AssetError, OSError) as exc:
        print(f'ERROR: {exc}')
        return 1
    errors = 0
    names = sorted({node.value for node in AnimationNode} | assets.clips.keys())
    for name in names:
        optional_missing = (name == 'yawn' and not args.strict
                            and name not in assets.clips and not (args.assets / name).exists())
        if optional_missing:
            print(f'OPTIONAL: {name} is absent')
            continue
        try:
            clip = assets.load(name)
            print(f'OK: {name}: {len(clip.frames)} frames, {sum(clip.durations_ms)} ms')
        except (AssetError, OSError) as exc:
            errors += 1
            print(f'ERROR: {name}: {exc}')
    return int(errors > 0)


if __name__ == '__main__':
    sys.exit(main())
