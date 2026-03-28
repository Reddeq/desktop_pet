import os
import json
import tempfile
import subprocess
import urllib.request
import urllib.error

from PyQt6.QtWidgets import QMessageBox

from version import __version__

# -----------------------------
# НАСТРОЙКИ
# -----------------------------
GITHUB_OWNER = "Reddeq"
GITHUB_REPO = "desktop_pet"
ASSET_NAME = "DesktopPetSetup.exe"   # имя файла, который ты прикладываешь к GitHub Release

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"


# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------
def normalize_version(version: str) -> str:
    return version.lstrip("vV").strip()


def version_tuple(version: str):
    return tuple(int(part) for part in normalize_version(version).split("."))


def get_latest_release_info():
    """
    Получает информацию о последнем релизе из GitHub.
    Возвращает словарь или None.
    """
    req = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ManulDesktopPet"
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
            if asset.get("name") == ASSET_NAME:
                asset_url = asset.get("browser_download_url")
                break

        if not tag_name:
            return None

        return {
            "version": normalize_version(tag_name),
            "tag_name": tag_name,
            "body": body,
            "asset_url": asset_url
        }

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def is_update_available():
    """
    Возвращает:
      (True, info)  -> если обновление есть
      (False, info) -> если обновления нет
      (False, None) -> если не удалось проверить
    """
    info = get_latest_release_info()
    if info is None:
        return False, None

    current = version_tuple(__version__)
    latest = version_tuple(info["version"])

    return latest > current, info


def download_update(asset_url: str):
    """
    Скачивает файл обновления во временную папку.
    Возвращает путь к файлу или None.
    """
    if not asset_url:
        return None

    target_path = os.path.join(tempfile.gettempdir(), ASSET_NAME)

    req = urllib.request.Request(
        asset_url,
        headers={
            "User-Agent": "ManulDesktopPet"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(target_path, "wb") as f:
                f.write(response.read())
        return target_path
    except urllib.error.URLError:
        return None


def run_installer(installer_path: str):
    """
    Запускает скачанный установщик.
    """
    if installer_path and os.path.exists(installer_path):
        subprocess.Popen([installer_path], shell=True)


# -----------------------------
# ГЛАВНАЯ ФУНКЦИЯ ДЛЯ ВЫЗОВА ИЗ UI
# -----------------------------
def check_for_updates(parent=None):
    """
    Полный сценарий:
    - проверка версии
    - предложение скачать
    - скачивание
    - запуск установщика
    """
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

    notes = info.get("body", "").strip()
    if not notes:
        notes = "Описание обновления отсутствует."

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
            "В последнем релизе не найден файл обновления."
        )
        return

    installer_path = download_update(asset_url)
    if not installer_path:
        QMessageBox.warning(
            parent,
            "Ошибка",
            "Не удалось скачать обновление."
        )
        return

    QMessageBox.information(
        parent,
        "Обновление загружено",
        "Установщик сейчас запустится."
    )
    run_installer(installer_path)

