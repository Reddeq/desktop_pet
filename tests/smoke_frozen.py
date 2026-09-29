"""Run against a *test* build: python tests/smoke_frozen.py path/to/DesktopPet.exe.

Installs one temporary external script, verifies discovery inside the actual EXE,
and removes the script afterwards. No window is displayed and no cursor is moved.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PROBE = '''import json
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from behavior_runtime import Scenario

class Behavior(Scenario):
    id = "smoke_frozen_probe"
    priority = 1000000

    @classmethod
    def probability(cls, controller, event):
        return float(event == "logic")

    def on_start(self):
        Path(os.environ["PET_SMOKE_RESULT"]).write_text(json.dumps({
            "ids": sorted(self.manager.registry),
            "errors": self.manager.errors,
            "frames_loaded": self.pet.animation_player.has_frames(),
        }))
        self.later(1, QApplication.instance().quit)
'''


def main():
    executable = Path(sys.argv[1]).resolve(strict=True)
    plugins = executable.parent / "behavior_plugins"
    plugins.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        result_path = Path(directory) / "result.json"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", prefix="smoke_", dir=plugins, delete=False) as script:
            script.write(PROBE)
        try:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PET_SMOKE_RESULT=str(result_path))
            result = subprocess.run(
                [str(executable)], env=env, cwd=executable.parent,
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            data = json.loads(result_path.read_text())
            assert not data["errors"], data
            assert data["frames_loaded"], data
            assert set(data["ids"]) == {
                "idle", "walk", "cleaning", "sleep", "meowing", "eating", "food_begging",
                "notifications", "hiding", "toilet", "zoomies", "menu_meowing", "smoke_frozen_probe",
            }, data
            print("Frozen EXE: 12 built-ins + one external script discovered and executed; assets loaded; clean exit.")
        finally:
            Path(script.name).unlink()


if __name__ == "__main__":
    main()
