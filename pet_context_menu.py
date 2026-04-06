from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QToolButton,
    QMessageBox,
    QStyle,
)
from PyQt6.QtGui import QIcon

from updater import check_for_updates


class PetQuickMenu(QWidget):
    def __init__(self, pet_widget):
        super().__init__(pet_widget)

        self.pet_widget = pet_widget

        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.panel = QFrame(self)
        self.panel.setObjectName("panel")
        root_layout.addWidget(self.panel)

        panel_layout = QHBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(10)

        style = QApplication.style()

        self.exit_button = self._make_square_button(
            text="Выход",
            icon=style.standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton),
            callback=self._on_exit,
        )

        self.info_button = self._make_square_button(
            text="О приложении",
            icon=style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation),
            callback=self._on_about,
        )

        self.help_button = self._make_square_button(
            text="Помощь",
            icon=style.standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton),
            callback=self._on_help,
        )

        panel_layout.addWidget(self.info_button)
        panel_layout.addWidget(self.help_button)
        panel_layout.addWidget(self.exit_button)

        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }

            QFrame#panel {
                background-color: rgba(28, 28, 32, 235);
                border: 1px solid rgba(255, 255, 255, 28);
                border-radius: 20px;
            }

            QToolButton {
                background-color: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 18px;
                color: white;
                font-size: 12px;
                font-weight: 600;
                padding: 8px;
            }

            QToolButton:hover {
                background-color: rgba(255, 255, 255, 22);
                border: 1px solid rgba(255, 255, 255, 36);
            }

            QToolButton:pressed {
                background-color: rgba(255, 255, 255, 30);
            }
            """
        )

    def _make_square_button(self, text: str, icon: QIcon, callback):
        button = QToolButton(self.panel)
        button.setText(text)
        button.setIcon(icon)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(28, 28))
        button.setFixedSize(92, 92)

        def wrapped():
            self.hide()
            callback()

        button.clicked.connect(wrapped)
        return button

    def show_at(self, global_pos: QPoint):
        if not self.isVisible():
            if hasattr(self.pet_widget, "controller"):
                self.pet_widget.controller.start_menu_meowing()

        self.adjustSize()

        screen = QApplication.screenAt(global_pos)
        if screen is None:
            screen = QApplication.primaryScreen()

        screen_rect = screen.availableGeometry()

        x = global_pos.x() + 8
        y = global_pos.y() + 8

        if x + self.width() > screen_rect.right():
            x = global_pos.x() - self.width() - 8

        if y + self.height() > screen_rect.bottom():
            y = global_pos.y() - self.height() - 8

        x = max(screen_rect.left(), min(x, screen_rect.right() - self.width()))
        y = max(screen_rect.top(), min(y, screen_rect.bottom() - self.height()))

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    # -------------------------
    # Actions
    # -------------------------

    def _on_exit(self):
        QApplication.instance().quit()

    def _on_about(self):
        QMessageBox.information(
            self.pet_widget,
            "О приложении",
            (
                "Desktop Pet — это манул-питомец на рабочем столе.\n\n"
                "Сейчас в проекте есть:\n"
                "• поведение по состояниям и нуждам\n"
                "• реакции на курсор\n"
                "• режим кормления\n"
                "• hiding / pooping / scratching / meowing\n"
                "• drag / falling / recovery\n"
            ),
        )

    def _on_help(self):
        QMessageBox.information(
            self.pet_widget,
            "Помощь",
            (
                "Управление:\n\n"
                "• ПКМ — открыть меню\n"
                "• Колесо мыши над манулом — смена режима курсора\n"
                "• GRAB — перетаскивание манула\n"
                "• FEED — кормление, если манул голоден\n\n"
                "Подсказка:\n"
                "Если запускаешь приложение из терминала, доступны debug-команды."
            ),
        )
    def hideEvent(self, event):
        super().hideEvent(event)

        if hasattr(self.pet_widget, "controller"):
            self.pet_widget.controller.finish_menu_meowing()


class PetContextMenuManager:
    def __init__(self, pet_widget):
        self.pet_widget = pet_widget
        self.menu = PetQuickMenu(pet_widget)

    def show(self, global_pos):
        self.menu.show_at(global_pos)