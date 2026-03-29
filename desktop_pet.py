import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QMenu
from PyQt6.QtGui import QAction, QGuiApplication, QIcon
from PyQt6.QtCore import Qt

from updater import check_for_updates
from animation_player import AnimationPlayer
from pet_controller import PetController
from pet_state import PetState


def get_resource_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


class FrameAnimatedPet(QWidget):
    def __init__(self):
        super().__init__()

        self.canvas_width = 220
        self.canvas_height = 220
        self.pet_render_height = 150

        self.current_state = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.assets_path = str(get_resource_base_dir() / "assets")
        self.icon_path = get_resource_base_dir() / "assets" / "icon.ico"

        self.label = QLabel(self)
        self.label.resize(self.canvas_width, self.canvas_height)
        self.resize(self.canvas_width, self.canvas_height)

        if self.icon_path.exists():
            self.setWindowIcon(QIcon(str(self.icon_path)))

        self.animation_player = AnimationPlayer(
            assets_path=self.assets_path,
            canvas_width=self.canvas_width,
            canvas_height=self.canvas_height,
            pet_render_height=self.pet_render_height,
            frame_interval=50,
            parent=self,
        )
        self.animation_player.frame_changed.connect(self.on_frame_changed)
        self.animation_player.animation_finished.connect(self.on_animation_finished)

        self.init_position()

        self.controller = PetController(self, self)
        self.controller.start()

        self.set_state(PetState.IDLE, force=True)
        self.show()

    def on_frame_changed(self, pixmap):
        self.label.setPixmap(pixmap)

    def on_animation_finished(self, animation_name: str):
        self.controller.on_animation_finished(animation_name)

    def init_position(self):
        screen_rect = self.get_current_screen_rect()
        start_x = screen_rect.x() + (screen_rect.width() - self.width()) // 2
        self.ground_y = screen_rect.y() + screen_rect.height() - self.height()
        self.move(start_x, self.ground_y)

    def get_current_screen_rect(self):
        center_point = self.frameGeometry().center()
        screen = QGuiApplication.screenAt(center_point)

        if screen is None:
            screen = QGuiApplication.primaryScreen()

        return screen.availableGeometry()

    def clamp_position(self, x, y):
        screen_rect = self.get_current_screen_rect()

        min_x = screen_rect.x()
        max_x = screen_rect.x() + screen_rect.width() - self.width()

        min_y = screen_rect.y()
        max_y = self.ground_y

        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))

        return x, y

    def set_state(self, new_state: PetState, force=False):
        if force or self.current_state != new_state:
            self.current_state = new_state
            self.animation_player.set_animation(new_state.value, force=force)

    def set_facing_right(self, value: bool):
        self.animation_player.set_facing_right(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.on_mouse_press(event.globalPosition())

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.controller.on_mouse_move(event.globalPosition())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.on_mouse_release()

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        update_action = QAction("Проверить обновления", self)
        update_action.triggered.connect(lambda: check_for_updates(self))
        menu.addAction(update_action)

        simulate_notice_action = QAction("Симулировать уведомление", self)
        simulate_notice_action.triggered.connect(
            self.controller.start_notification_investigation
        )
        menu.addAction(simulate_notice_action)

        menu.addSeparator()

        exit_action = QAction("Убрать манула", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        menu.exec(event.globalPos())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = FrameAnimatedPet()
    sys.exit(app.exec())