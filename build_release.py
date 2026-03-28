import shutil
import subprocess
import zipfile
from pathlib import Path

try:
    from version import __version__
except Exception:
    __version__ = "0.1.0"


PROJECT_NAME = "DesktopPet"
ENTRY_SCRIPT = "desktop_pet.py"
ASSETS_ARG = "assets:assets"


def zip_directory_contents(source_dir: Path, zip_path: Path):
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in source_dir.rglob("*"):
            if path.is_file():
                arcname = path.relative_to(source_dir)
                zf.write(path, arcname)


def main():
    root = Path(__file__).resolve().parent
    dist_dir = root / "dist"
    build_dir = root / "build"
    release_dir = root / "release"
    spec_file = root / f"{PROJECT_NAME}.spec"
    app_dir = dist_dir / PROJECT_NAME

    versioned_zip = release_dir / f"{PROJECT_NAME}-v{__version__}-win64.zip"
    stable_zip = release_dir / f"{PROJECT_NAME}-win64.zip"

    # Чистим старые артефакты
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)

    if app_dir.exists():
        shutil.rmtree(app_dir, ignore_errors=True)

    if spec_file.exists():
        spec_file.unlink()

    release_dir.mkdir(parents=True, exist_ok=True)

    print("[1/3] Сборка приложения через PyInstaller...")
    cmd = [
        "pyinstaller",
        "-D",
        "-w",
        "-n", PROJECT_NAME,
        "--clean",
        "--add-data", ASSETS_ARG,
        ENTRY_SCRIPT,
    ]
    subprocess.run(cmd, check=True)

    if not app_dir.exists():
        raise RuntimeError(f"Не найдена папка сборки: {app_dir}")

    print("[2/3] Создание versioned ZIP...")
    if versioned_zip.exists():
        versioned_zip.unlink()
    zip_directory_contents(app_dir, versioned_zip)

    print("[3/3] Создание stable ZIP для updater...")
    if stable_zip.exists():
        stable_zip.unlink()
    shutil.copy2(versioned_zip, stable_zip)

    print()
    print("Готово.")
    print(f"Версионный архив: {versioned_zip}")
    print(f"Стабильный архив: {stable_zip}")

if __name__ == "__main__":
    main()

