import json
import os
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
    return version.lstrip("vV").strip()


def version_tuple(version: str):
    return tuple(int(part) for part in normalize_version(version).split("."))


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
        body = data.get("body", "")
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

    current = version_tuple(__version__)
    latest = version_tuple(info["version"])

    return latest > current, info


def download_zip(asset_url: str) -> str | None:
    if not asset_url:
        return None

    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, ZIP_ASSET_NAME)

    req = urllib.request.Request(
        asset_url,
        headers={"User-Agent": "DesktopPetUpdater"}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            with open(zip_path, "wb") as f:
                f.write(response.read())
        return zip_path
    except urllib.error.URLError:
        return None


def extract_zip(zip_path: str) -> str | None:
    if not os.path.exists(zip_path):
        return None

    extract_dir = os.path.join(tempfile.gettempdir(), "DesktopPet_update")
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir, ignore_errors=True)

    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        return extract_dir
    except zipfile.BadZipFile:
        return None


def get_current_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def create_update_script(source_dir: Path, target_dir: Path, exe_name: str) -> Path:
    script_path = Path(tempfile.gettempdir()) / "desktoppet_apply_update.bat"

    script = f"""@echo off
chcp 65001 >nul
echo Applying update...
timeout /t 2 /nobreak >nul
robocopy "{source_dir}" "{target_dir}" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
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

    extracted_dir = extract_zip(zip_path)
    if not extracted_dir:
        QMessageBox.warning(
            parent,
            "Ошибка",
            "Не удалось распаковать обновление."
        )
        return

    current_app_dir = get_current_app_dir()
    exe_name = Path(sys.executable).name

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