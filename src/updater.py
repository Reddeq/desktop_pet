import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

from PyQt6.QtWidgets import QMessageBox, QApplication

from version import __version__

GITHUB_OWNER = "Reddeq"
GITHUB_REPO = "desktop_pet"
ZIP_ASSET_NAME = "DesktopPet-win64.zip"

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


def normalize_version(version: str) -> str:
    return version.strip().lstrip("vV")


def version_tuple(version: str):
    normalized = normalize_version(version)
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", normalized):
        raise ValueError(f"Unsupported release version: {version!r}")
    parts = tuple(int(part) for part in normalized.split("."))
    return parts + (0,) * (4 - len(parts))


def get_latest_release_info():
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DesktopPetUpdater"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        tag_name = data.get("tag_name", "").strip()
        body = data.get("body") or ""
        assets = data.get("assets", [])

        asset_url = None
        for asset in assets:
            if asset.get("name") == ZIP_ASSET_NAME:
                asset_url = asset.get("browser_download_url")
                break

        if not tag_name:
            return None

        return {
            "version": normalize_version(tag_name),
            "tag_name": tag_name,
            "body": body,
            "asset_url": asset_url,
        }

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def is_update_available():
    info = get_latest_release_info()
    if info is None:
        return False, None

    try:
        current = version_tuple(__version__)
        latest = version_tuple(info["version"])
    except (TypeError, ValueError):
        return False, None
    return latest > current, info


def download_zip(asset_url: str) -> str | None:
    if not asset_url:
        return None

    req = urllib.request.Request(asset_url, headers={"User-Agent": "DesktopPetUpdater"})
    zip_path = None
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            with tempfile.NamedTemporaryFile(prefix="DesktopPet-", suffix=".zip", delete=False) as output:
                zip_path = Path(output.name)
                shutil.copyfileobj(response, output)
        return str(zip_path)
    except (OSError, urllib.error.URLError):
        if zip_path is not None:
            zip_path.unlink(missing_ok=True)
        return None


def extract_zip(zip_path: str) -> str | None:
    """Stage in a unique directory and reject ambiguous/traversing members."""
    extract_dir = Path(tempfile.mkdtemp(prefix="DesktopPet-update-"))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                parts = name.rstrip("/").split("/")
                if (name.startswith("/") or any(part in {"", ".", ".."} or ":" in part for part in parts)
                        or not (extract_dir / name).resolve().is_relative_to(extract_dir)):
                    raise ValueError(f"Unsafe archive member: {name}")
            archive.extractall(extract_dir)
        return str(extract_dir)
    except (OSError, ValueError, zipfile.BadZipFile):
        shutil.rmtree(extract_dir)
        return None


def get_current_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def create_update_script(source_dir: Path, target_dir: Path, exe_name: str) -> Path:
    with tempfile.NamedTemporaryFile(prefix="desktoppet-update-", suffix=".bat", delete=False) as output:
        script_path = Path(output.name)

    script = f"""@echo off
chcp 65001 >nul
echo Applying update...
timeout /t 2 /nobreak >nul
robocopy "{source_dir}" "{target_dir}" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 exit /b 1
start "" "{target_dir / exe_name}"
exit
"""

    script_path.write_text(script, encoding="utf-8")
    return script_path


def run_update_script(script_path: Path):
    subprocess.Popen(
        ["cmd", "/c", str(script_path)],
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def check_for_updates(parent=None):
    if not getattr(sys, "frozen", False):
        QMessageBox.information(
            parent,
            "Обновления",
            "Проверка обновлений работает только в собранной версии приложения."
        )
        return

    has_update, info = is_update_available()

    if info is None:
        QMessageBox.information(
            parent,
            "Обновления",
            "Не удалось проверить обновления."
        )
        return

    if not has_update:
        QMessageBox.information(
            parent,
            "Обновления",
            f"У вас уже последняя версия: {__version__}"
        )
        return

    notes = info.get("body", "").strip() or "Описание обновления отсутствует."

    reply = QMessageBox.question(
        parent,
        "Доступно обновление",
        f"Текущая версия: {__version__}\n"
        f"Новая версия: {info['version']}\n\n"
        f"Что нового:\n{notes[:500]}\n\n"
        f"Скачать и установить обновление?"
    )

    if reply != QMessageBox.StandardButton.Yes:
        return

    asset_url = info.get("asset_url")
    if not asset_url:
        QMessageBox.warning(
            parent,
            "Ошибка",
            f"В последнем релизе не найден файл {ZIP_ASSET_NAME}."
        )
        return

    zip_path = download_zip(asset_url)
    if not zip_path:
        QMessageBox.warning(
            parent,
            "Ошибка",
            "Не удалось скачать обновление."
        )
        return

    try:
        extracted_dir = extract_zip(zip_path)
    finally:
        Path(zip_path).unlink(missing_ok=True)
    if not extracted_dir:
        QMessageBox.warning(
            parent,
            "Ошибка",
            "Не удалось распаковать обновление."
        )
        return

    current_app_dir = get_current_app_dir()
    exe_name = Path(sys.executable).name

    if not (Path(extracted_dir) / exe_name).is_file():
        QMessageBox.warning(parent, "Ошибка", "Архив не содержит исполняемый файл приложения.")
        shutil.rmtree(extracted_dir)
        return

    script_path = create_update_script(
        source_dir=Path(extracted_dir),
        target_dir=current_app_dir,
        exe_name=exe_name
    )

    QMessageBox.information(
        parent,
        "Обновление загружено",
        "Приложение сейчас закроется, обновится и запустится снова."
    )

    run_update_script(script_path)

    app = QApplication.instance()
    if app is not None:
        app.quit()