"""Validated clip descriptions and bounded cache, independent of playback."""
import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QTransform


class AssetError(ValueError):
    pass


def positive_int(value, label):
    if type(value) is not int or not 1 <= value <= 2_147_483_647:
        raise AssetError(f"{label} must be a positive integer")
    return value


def natural_key(path):
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r"(\d+)", path.name))


@dataclass(frozen=True)
class AnimationClip:
    frames: tuple[QPixmap, ...]
    durations_ms: tuple[int, ...]


class AnimationAssets:
    """Optional animations.json overrides legacy <name>/*.png directories.

    Call on the GUI thread. QPixmap frames are implicitly shared by Qt.
    Clips larger than the cache budget work but aren't retained in the cache.
    """

    def __init__(self, root, scale=0.5, interval=50, cache_bytes=64 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.scale = scale
        self.interval = positive_int(interval, "frame interval")
        self.cache_bytes = cache_bytes
        self._cache = OrderedDict()
        self._size = 0
        self.defaults = {}
        self.clips = {}
        manifest = self.root / "animations.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise AssetError(f"{manifest}: {exc}") from exc
            if not isinstance(data, dict) or data.get("version") != 1:
                raise AssetError("animations.json requires version: 1")
            self.defaults = data.get("defaults", {})
            self.clips = data.get("clips", {})
            if not isinstance(self.defaults, dict) or not isinstance(self.clips, dict):
                raise AssetError("defaults and clips must be objects")
            if set(self.defaults) - {"scale", "pixel_art", "frame_ms"}:
                raise AssetError("Unknown animation default")

    def _path(self, name):
        if not isinstance(name, str) or not name:
            raise AssetError("Asset path must be a non-empty string")
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise AssetError(f"Asset path escapes assets directory: {name}")
        return path

    def load(self, name, facing_right=True):
        key = (name, facing_right, self.interval)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key][0]
        options = self.clips.get(name, {})
        if not isinstance(options, dict):
            raise AssetError(f"{name}: clip must be an object")
        if set(options) - {"directory", "sheet", "frame_size", "count", "scale", "pixel_art", "frame_ms", "durations_ms"}:
            raise AssetError(f"{name}: unknown clip option")
        options = self.defaults | options
        scale = options.get("scale", self.scale)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise AssetError(f"{name}: scale must be positive and finite")
        pixel_art = options.get("pixel_art", False)
        if type(pixel_art) is not bool:
            raise AssetError(f"{name}: pixel_art must be boolean")
        if pixel_art and (scale < 1 or not float(scale).is_integer()):
            raise AssetError(f"{name}: pixel art requires an integer scale >= 1")
        interval = positive_int(options.get("frame_ms", self.interval), "frame_ms")
        if "sheet" in options:
            if "directory" in options:
                raise AssetError(f"{name}: choose sheet or directory")
            size = options.get("frame_size")
            if not isinstance(size, list) or len(size) != 2:
                raise AssetError(f"{name}: frame_size must be [width, height]")
            width, height = [positive_int(v, "frame_size") for v in size]
            sheet = self._read(self._path(options["sheet"]))
            if sheet.width() % width or sheet.height() % height:
                raise AssetError(f"{name}: sheet size must be divisible by frame_size")
            columns, rows = sheet.width() // width, sheet.height() // height
            count = positive_int(options.get("count", columns * rows), "count")
            if count > columns * rows:
                raise AssetError(f"{name}: count exceeds sheet capacity")
            frames = [sheet.copy(i % columns * width, i // columns * height, width, height) for i in range(count)]
        else:
            if "frame_size" in options or "count" in options:
                raise AssetError(f"{name}: frame_size/count require sheet")
            directory = self._path(options.get("directory", name))
            if not directory.is_dir():
                raise AssetError(f"{name}: missing directory {directory}")
            files = sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".png"), key=lambda p: (natural_key(p), p.name))
            frames = [self._read(self._path(str(p))) for p in files]
        if not frames:
            raise AssetError(f"{name}: no PNG frames")
        if any(frame.size() != frames[0].size() for frame in frames):
            raise AssetError(f"{name}: use a fixed canvas size for all frames")
        durations = options.get("durations_ms", [interval] * len(frames))
        if not isinstance(durations, list) or len(durations) != len(frames):
            raise AssetError(f"{name}: durations_ms must match the frame count")
        durations = tuple(positive_int(v, "duration") for v in durations)
        mode = Qt.TransformationMode.FastTransformation if pixel_art else Qt.TransformationMode.SmoothTransformation
        rendered = []
        for frame in frames:
            if not facing_right:
                frame = frame.transformed(QTransform().scale(-1, 1), Qt.TransformationMode.FastTransformation)
            width, height = frame.width() * scale, frame.height() * scale
            if not math.isfinite(width) or not math.isfinite(height) or max(width, height) > 16384:
                raise AssetError(f"{name}: rendered frame exceeds 16384 pixels per side")
            frame = frame.scaled(max(1, int(width)), max(1, int(height)), Qt.AspectRatioMode.IgnoreAspectRatio, mode)
            rendered.append(frame)
        clip = AnimationClip(tuple(rendered), durations)
        cost = sum(p.width() * p.height() * 4 for p in rendered)
        if cost <= self.cache_bytes:
            while self._cache and self._size + cost > self.cache_bytes:
                _, (_, old_cost) = self._cache.popitem(last=False)
                self._size -= old_cost
            self._cache[key] = (clip, cost)
            self._size += cost
        return clip

    @staticmethod
    def _read(path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise AssetError(f"Unreadable PNG: {path}")
        return pixmap

    def clear_cache(self):
        self._cache.clear()
        self._size = 0
