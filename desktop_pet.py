import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtCore import Qt, QEvent

from animation_node import AnimationNode
from animation_player import AnimationPlayer
from interaction_cursors import InteractionCursorManager
from interaction_mode import InteractionMode
from pet_animator import PetAnimator
from pet_context_menu import PetContextMenuManager
from pet_controller import PetController
from pet_state import PetState
from debug_console import DebugConsole


def get_resource_base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


class FrameAnimatedPet(QWidget):
    def __init__(self):
        super().__init__()

        self.scale_factor = 0.3

        # Пока оставляем current_state как high-level logical state,
        # потому что controller / needs ещё используют его.
        self.current_state: PetState | None = None

        self._position_initialized = False
        self.horizontal_edge_anchor = None   # None | "left" | "right"
        self.bound_screen = None
        self.drag_locked_screen = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.base_dir = get_resource_base_dir()
        self.assets_path = str(self.base_dir / "assets")
        self.icon_path = self.base_dir / "assets" / "icon.ico"

        self.cursors = InteractionCursorManager(self.base_dir)
        self.context_menu = PetContextMenuManager(self)

        self.label = QLabel(self)
        self.label.installEventFilter(self)

        if self.icon_path.exists():
            self.setWindowIcon(QIcon(str(self.icon_path)))

        self.animation_player = AnimationPlayer(
            assets_path=self.assets_path,
            scale_factor=self.scale_factor,
            frame_interval=50,
            parent=self,
        )
        self.animation_player.frame_changed.connect(self.on_frame_changed)
        self.animation_player.animation_finished.connect(self.on_animation_finished)

        self.animator = PetAnimator(
            pet=self,
            animation_player=self.animation_player,
            parent=self,
        )

        # Стартовый animation node — уже по новой системе
        self.animator.set_initial_node(AnimationNode.SITTING_IDLE)

        self.controller = PetController(self, self)
        self.controller.start()

        self.debug_console = DebugConsole(self.controller, self)
        self.debug_console.start()

        # Стартовое логическое состояние — пока оставляем для старых модулей
        self.current_state = PetState.IDLE

        self.init_position()
        self._position_initialized = True

        self.show()

    # -------------------------
    # Animation-facing API (new)
    # -------------------------

    def play_sequence_nodes(
        self,
        target_sequence: list[AnimationNode],
        replace: bool = True,
        force_restart: bool = False,
    ):
        self.animator.play_sequence_nodes(
            target_sequence=target_sequence,
            replace=replace,
            force_restart=force_restart,
        )

    def play_node(
        self,
        node: AnimationNode,
        replace: bool = True,
        force_restart: bool = False,
    ):
        self.play_sequence_nodes(
            [node],
            replace=replace,
            force_restart=force_restart,
        )

    def force_set_animation_node(self, node: AnimationNode, hold: bool = True):
        self.animator.force_set_node(node=node, hold=hold)

    def interrupt_animation(
        self,
        node: AnimationNode,
        recovery_targets: list[AnimationNode] | None = None,
    ):
        self.animator.interrupt_with(
            node=node,
            recovery_targets=recovery_targets,
        )

    def resolve_animation_interrupt(self):
        self.animator.resolve_interrupt()

    def current_animation_node(self) -> AnimationNode | None:
        return self.animator.current_node

    # -------------------------
    # Legacy logical-state bridge (temporary)
    # -------------------------

    def set_state(self, new_state: PetState, force: bool = False):
        """
        ВРЕМЕННЫЙ мост для старых модулей (controller / motion / cursor_ai / needs),
        которые пока ещё думают в PetState.

        После переписывания этих модулей этот метод можно удалить.
        """
        if force or self.current_state != new_state:
            self.current_state = new_state
            self.animator.request_state(new_state, force=force)

    # -------------------------
    # Facing / orientation
    # -------------------------

    def set_facing_right(self, value: bool):
        self.animation_player.set_facing_right(value)

    # -------------------------
    # Animation / state hooks
    # -------------------------

    def on_frame_changed(self, pixmap):
        if self._position_initialized:
            old_bottom = self.y() + self.height()
        else:
            old_bottom = None

        self.label.setPixmap(pixmap)
        self.label.resize(pixmap.size())
        self.resize(pixmap.size())

        if self._position_initialized and old_bottom is not None:
            new_y = old_bottom - self.height()
            self.move(self.x(), new_y)

            # Если есть edge-anchor, после resize удерживаем нужный край
            self.snap_to_edge_anchor()

            screen_rect = self.get_current_screen_rect()
            self.ground_y = screen_rect.y() + screen_rect.height() - self.height()

    def on_animation_finished(self, animation_name: str):
        # Сначала даём аниматору обработать очередь / interrupt / transitions
        self.animator.on_animation_finished(animation_name)

        # Затем остальной логике поведения
        self.controller.on_animation_finished(animation_name)

    def get_screen_for_point(self, global_point):
        screen = QGuiApplication.screenAt(global_point)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen

    def get_bound_screen(self):
        """
        Экран-владелец манула.
        Если ещё не задан — определяем по центру окна.
        """
        if self.bound_screen is not None:
            return self.bound_screen

        center_point = self.frameGeometry().center()
        self.bound_screen = self.get_screen_for_point(center_point)
        return self.bound_screen

    def bind_to_screen(self, screen):
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        self.bound_screen = screen

    def lock_drag_to_current_screen(self):
        self.drag_locked_screen = self.get_bound_screen()

    def unlock_drag_screen(self):
        self.drag_locked_screen = None

    def get_active_clamp_screen(self):
        """
        Во время drag clamp идёт по экрану, на котором манула схватили.
        В остальное время — по bound_screen.
        """
        if self.drag_locked_screen is not None:
            return self.drag_locked_screen
        return self.get_bound_screen()

    # -------------------------
    # Geometry / positioning
    # -------------------------

    def init_position(self):
        screen = QGuiApplication.primaryScreen()
        self.bind_to_screen(screen)

        screen_rect = screen.availableGeometry()
        start_x = screen_rect.x() + (screen_rect.width() - self.width()) // 2
        self.ground_y = screen_rect.y() + screen_rect.height() - self.height()
        self.move(start_x, self.ground_y)

    def get_current_screen_rect(self):
        screen = self.get_active_clamp_screen()
        return screen.availableGeometry()

    def clamp_position(self, x, y):
        screen_rect = self.get_current_screen_rect()

        min_x = screen_rect.x()
        max_x = screen_rect.x() + screen_rect.width() - self.width()

        min_y = screen_rect.y()
        max_y = screen_rect.y() + screen_rect.height() - self.height()

        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))

        return x, y

    # -------------------------
    # Event filter for label
    # -------------------------

    def eventFilter(self, obj, event):
        if obj is self.label:
            if event.type() == QEvent.Type.Enter:
                self.cursors.apply_to_widget(self)
                return False

            if event.type() == QEvent.Type.Leave:
                self.cursors.clear_from_widget(self)
                return False

            if event.type() == QEvent.Type.Wheel:
                if self.cursors.is_cursor_over_widget(self):
                    delta_y = event.angleDelta().y()

                    if delta_y > 0:
                        self.cursors.cycle_mode(+1)
                    elif delta_y < 0:
                        self.cursors.cycle_mode(-1)

                    self.cursors.apply_to_widget(self)
                    event.accept()
                    return True

            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.cursors.current_mode() == InteractionMode.GRAB:
                        self.setCursor(self.cursors.get_drag_cursor())
                        self.controller.on_mouse_press(event.globalPosition())
                        return True

                    if event.type() == QEvent.Type.MouseButtonPress:
                        if event.button() == Qt.MouseButton.LeftButton:
                            if self.cursors.current_mode() == InteractionMode.GRAB:
                                self.setCursor(self.cursors.get_drag_cursor())
                                self.controller.on_mouse_press(event.globalPosition())
                                return True

                            if self.cursors.current_mode() == InteractionMode.FEED:
                                self.controller.try_feed()
                                event.accept()
                                return True

            if event.type() == QEvent.Type.MouseMove:
                if event.buttons() == Qt.MouseButton.LeftButton:
                    if self.cursors.current_mode() == InteractionMode.GRAB:
                        self.controller.on_mouse_move(event.globalPosition())
                        return True

                    if self.cursors.current_mode() == InteractionMode.FEED:
                        event.accept()
                        return True

            if event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.cursors.current_mode() == InteractionMode.GRAB:
                        self.controller.on_mouse_release()
                        self.cursors.apply_to_widget(self)
                        return True

                    if self.cursors.current_mode() == InteractionMode.FEED:
                        event.accept()
                        self.cursors.apply_to_widget(self)
                        return True

        return super().eventFilter(obj, event)

    # -------------------------
    # Mouse handling fallback
    # -------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.cursors.current_mode() == InteractionMode.GRAB:
                self.setCursor(self.cursors.get_drag_cursor())
                self.controller.on_mouse_press(event.globalPosition())
                return

            if self.cursors.current_mode() == InteractionMode.FEED:
                self.controller.try_feed()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.cursors.current_mode() == InteractionMode.GRAB:
                self.controller.on_mouse_move(event.globalPosition())
                return

            if self.cursors.current_mode() == InteractionMode.FEED:
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
       if event.button() == Qt.MouseButton.LeftButton:
            if self.cursors.current_mode() == InteractionMode.GRAB:
                self.controller.on_mouse_release()
                self.cursors.apply_to_widget(self)
                return

            if self.cursors.current_mode() == InteractionMode.FEED:
                event.accept()
                self.cursors.apply_to_widget(self)
                return

       super().mouseReleaseEvent(event)

    # -------------------------
    # Context menu
    # -------------------------

    def contextMenuEvent(self, event):
        self.context_menu.show(event.globalPos())

    def get_screen_for_point(self, global_point):
        screen = QGuiApplication.screenAt(global_point)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen

    def clamp_position_to_screen(self, x, y, screen):
        screen_rect = screen.availableGeometry()

        min_x = screen_rect.x()
        max_x = screen_rect.x() + screen_rect.width() - self.width()

        min_y = screen_rect.y()
        max_y = screen_rect.y() + screen_rect.height() - self.height()

        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))

        return x, y

    def clamp_position_for_drag(self, x, y, cursor_global_point):
        """
        Во время drag выбираем экран по текущей позиции курсора,
        а затем clamp'им манула целиком внутрь этого экрана.

        Так можно переносить манула между мониторами,
        но нельзя оставить его "разрезанным" между ними.
        """
        screen = self.get_screen_for_point(cursor_global_point)
        self.bind_to_screen(screen)
        return self.clamp_position_to_screen(x, y, screen)

    def set_horizontal_edge_anchor(self, edge: str | None):
        """
        edge:
          - None
          - "left"
          - "right"
        """
        self.horizontal_edge_anchor = edge

    def snap_to_edge_anchor(self):
        """
        Пересчитывает X по активному edge-anchor.
        """
        if self.horizontal_edge_anchor is None:
            return

        screen_rect = self.get_current_screen_rect()

        if self.horizontal_edge_anchor == "left":
            new_x = screen_rect.x()
        elif self.horizontal_edge_anchor == "right":
            new_x = screen_rect.x() + screen_rect.width() - self.width()
        else:
            return

        self.move(new_x, self.y())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = FrameAnimatedPet()
    sys.exit(app.exec())