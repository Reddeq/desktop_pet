import sys
import os
import random
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QMenu
from PyQt6.QtGui import QPixmap, QAction, QGuiApplication, QTransform, QPainter
from PyQt6.QtCore import Qt, QTimer, QPoint
from updater import check_for_updates


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

        self.gravity_speed = 0
        self.is_falling = False
        self.facing_right = True
        self.is_walking = False
        self.walk_direction = 1
        self.walk_target_x = 0
        self.walk_speed = 4
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.assets_path = str(get_resource_base_dir() / "assets")

        self.current_state = "idle"
        self.current_frame_index = 0
        self.frames = []

        self.label = QLabel(self)

        self.load_frames(self.current_state)
        self.update_frame()
        self.resize_to_frame()

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.next_frame)
        self.anim_timer.start(50)

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self.pet_logic)
        self.logic_timer.start(5000)

        self.gravity_timer = QTimer(self)
        self.gravity_timer.timeout.connect(self.apply_gravity)
        self.gravity_timer.start(20)

        self.walk_timer = QTimer(self)
        self.walk_timer.timeout.connect(self.process_walk_step)
        self.walk_timer.start(16)

        self.init_position()

        self.show()

    def init_position(self):
        screen_rect = self.get_current_screen_rect()

        start_x = screen_rect.x() + (screen_rect.width() - self.width()) // 2
        self.ground_y = screen_rect.y() + screen_rect.height() - self.height()

        self.move(start_x, self.ground_y)

    def apply_gravity(self):
        if not self.is_falling:
            return

        if self.y() < self.ground_y:
            self.gravity_speed += 2
            new_y = self.y() + self.gravity_speed

            if new_y >= self.ground_y:
                new_y = self.ground_y
                self.is_falling = False
                self.gravity_speed = 0

            self.move(self.x(), new_y)
        else:
            self.is_falling = False
            self.gravity_speed = 0

    def load_frames(self, state_name):
        self.frames = []
        path = os.path.join(self.assets_path, state_name)

        if not os.path.exists(path):
            return

        files = sorted([f for f in os.listdir(path) if f.endswith(".png")])

        for file in files:
            full_path = os.path.join(path, file)
            pixmap = QPixmap(full_path)

            if pixmap.isNull():
                continue

            if state_name in {"walk", "idle"} and not self.facing_right:
                pixmap = pixmap.transformed(
                    QTransform().scale(-1, 1),
                    Qt.TransformationMode.SmoothTransformation
                )

            scaled_pixmap = pixmap.scaledToHeight(
                self.pet_render_height,
                Qt.TransformationMode.SmoothTransformation
            )

            canvas = QPixmap(self.canvas_width, self.canvas_height)
            canvas.fill(Qt.GlobalColor.transparent)

            painter = QPainter(canvas)

            x = (self.canvas_width - scaled_pixmap.width()) // 2
            y = self.canvas_height - scaled_pixmap.height()

            painter.drawPixmap(x, y, scaled_pixmap)
            painter.end()

            self.frames.append(canvas)

        self.current_frame_index = 0
    
    def update_frame(self):
        if self.frames:
            pixmap = self.frames[self.current_frame_index]
            self.label.setPixmap(pixmap)

    def next_frame(self):
        if len(self.frames) > 1:
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
            self.update_frame()

    def resize_to_frame(self):
        if self.frames:
            size = self.frames[0].size()
            self.label.resize(size)
            self.resize(size)

    def set_state(self, new_state):
        if self.current_state != new_state:
            self.current_state = new_state
            self.load_frames(new_state)
            self.resize_to_frame()
            self.update_frame()

    def pet_logic(self):
        if self.is_falling or self.is_walking:
            return

        choices = ["idle", "walk"]
        weights = [0.7, 0.3]
        new_action = random.choices(choices, weights=weights)[0]

        if new_action == "walk":
            direction = random.choice([-1, 1])
            distance = random.randint(60, 180)

            self.walk_direction = direction
            self.facing_right = (direction == 1)

            self.set_state("walk")

            target_x = self.x() + (direction * distance)
            target_x, _ = self.clamp_position(target_x, self.ground_y)

            if target_x == self.x():
                self.set_state("idle")
                return

            self.walk_target_x = target_x
            self.is_walking = True

        else:
            self.set_state("idle")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_falling = False
            self.gravity_speed = 0

            self.is_walking = False

            self.old_pos = event.globalPosition().toPoint()
            self.set_state("idle")

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = QPoint(event.globalPosition().toPoint() - self.old_pos)

            new_x = self.x() + delta.x()
            new_y = self.y() + delta.y()

            new_x, new_y = self.clamp_position(new_x, new_y)

            self.move(new_x, new_y)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.y() > self.ground_y:
                self.move(self.x(), self.ground_y)

            if self.y() < self.ground_y:
                self.is_falling = True

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        update_action = QAction("Проверить обновления", self)
        update_action.triggered.connect(lambda: check_for_updates(self))
        menu.addAction(update_action)

        menu.addSeparator()

        exit_action = QAction("Убрать манула", self)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        menu.exec(event.globalPos())

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

    def process_walk_step(self):
        if not self.is_walking:
            return

        current_x = self.x()

        if self.walk_direction == 1:
            new_x = min(current_x + self.walk_speed, self.walk_target_x)
        else:
            new_x = max(current_x - self.walk_speed, self.walk_target_x)

        new_x, new_y = self.clamp_position(new_x, self.ground_y)
        self.move(new_x, new_y)

        if new_x == self.walk_target_x:
            self.is_walking = False
            self.set_state("idle")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = FrameAnimatedPet()
    sys.exit(app.exec())