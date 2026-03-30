import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QMenu
from PyQt6.QtGui import QAction, QGuiApplication, QIcon, QCursor, QPixmap
from PyQt6.QtCore import Qt, QEvent

from updater import check_for_updates
from animation_player import AnimationPlayer
from pet_controller import PetController
from pet_state import PetState
from interaction_mode import InteractionMode


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

        base_dir = get_resource_base_dir()
        self.assets_path = str(base_dir / "assets")
        self.icon_path = base_dir / "assets" / "icon.ico"

        self.interaction_mode = InteractionMode.GRAB

        self.grab_cursor = QCursor(Qt.CursorShape.OpenHandCursor)
        self.grab_drag_cursor = QCursor(Qt.CursorShape.ClosedHandCursor)

        feed_cursor_path = base_dir / "assets" / "cursors" / "meat_cursor.png"
        if feed_cursor_path.exists():
            self.feed_cursor = QCursor(QPixmap(str(feed_cursor_path)), 0, 0)
        else:
            self.feed_cursor = QCursor(Qt.CursorShape.PointingHandCursor)

        self.label = QLabel(self)
        self.label.resize(self.canvas_width, self.canvas_height)
        self.resize(self.canvas_width, self.canvas_height)

        self.label.installEventFilter(self)

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


    def cycle_interaction_mode(self, direction: int):
        modes = [
            InteractionMode.GRAB,
            InteractionMode.FEED,
        ]

        current_index = modes.index(self.interaction_mode)
        new_index = (current_index + direction) % len(modes)

        self.interaction_mode = modes[new_index]
        self.apply_interaction_cursor()

    def get_current_interaction_cursor(self) -> QCursor:
        if self.interaction_mode == InteractionMode.FEED:
            return self.feed_cursor

        return self.grab_cursor

    def is_cursor_over_pet(self) -> bool:
        global_pos = QCursor.pos()
        local_pos = self.mapFromGlobal(global_pos)
        return self.rect().contains(local_pos)

    def apply_interaction_cursor(self):
        if self.is_cursor_over_pet():
            self.setCursor(self.get_current_interaction_cursor())
        else:
            self.unsetCursor()


    def eventFilter(self, obj, event):
        if obj is self.label:
            if event.type() == QEvent.Type.Enter:
                self.apply_interaction_cursor()
                return False

            if event.type() == QEvent.Type.Leave:
                self.unsetCursor()
                return False

            if event.type() == QEvent.Type.Wheel:
                if self.is_cursor_over_pet():
                    delta_y = event.angleDelta().y()

                    if delta_y > 0:
                        self.cycle_interaction_mode(+1)
                    elif delta_y < 0:
                        self.cycle_interaction_mode(-1)

                    event.accept()
                    return True

        return super().eventFilter(obj, event)


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.interaction_mode == InteractionMode.GRAB:
                self.setCursor(self.grab_drag_cursor)
                self.controller.on_mouse_press(event.globalPosition())
                return

            if self.interaction_mode == InteractionMode.FEED:
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.interaction_mode == InteractionMode.GRAB:
                self.controller.on_mouse_move(event.globalPosition())
                return

            if self.interaction_mode == InteractionMode.FEED:
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.interaction_mode == InteractionMode.GRAB:
                self.controller.on_mouse_release()
                self.apply_interaction_cursor()
                return

            if self.interaction_mode == InteractionMode.FEED:
                event.accept()
                self.apply_interaction_cursor()
                return

        super().mouseReleaseEvent(event)


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