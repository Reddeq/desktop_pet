from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtGui import QAction

from updater import check_for_updates


class PetContextMenuManager:
    def __init__(self, pet_widget):
        self.pet_widget = pet_widget

    def show(self, global_pos):
        menu = QMenu(self.pet_widget)

        update_action = QAction("Проверить обновления", self.pet_widget)
        update_action.triggered.connect(lambda: check_for_updates(self.pet_widget))
        menu.addAction(update_action)

        simulate_notice_action = QAction("Симулировать уведомление", self.pet_widget)
        simulate_notice_action.triggered.connect(
            self.pet_widget.controller.start_notification_investigation
        )
        menu.addAction(simulate_notice_action)

        show_needs_action = QAction("Показать потребности", self.pet_widget)
        show_needs_action.triggered.connect(self.debug_print_needs)
        menu.addAction(show_needs_action)

        menu.addSeparator()

        exit_action = QAction("Убрать манула", self.pet_widget)
        exit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(exit_action)

        menu.exec(global_pos)

    def debug_print_needs(self):
        needs = self.pet_widget.controller.needs.snapshot()

        print("=== Потребности манула ===")
        print(f"Состояние: {self.pet_widget.current_state}")
        print(f"Сытость   (satiety): {needs['satiety']:.2f}")
        print(f"Бодрость  (energy):  {needs['energy']:.2f}")
        print(f"Настроение(mood):    {needs['mood']:.2f}")
        print(f"Туалет    (bladder): {needs['bladder']:.2f}")
        print("==========================")
