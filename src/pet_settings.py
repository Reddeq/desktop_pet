"""Persistent user preferences, separate from bundled application resources."""
from PyQt6.QtCore import QSettings


class PetSettings:
    def __init__(self, store=None):
        self.store = store if store is not None else QSettings('Reddeq', 'Pixler')

    @property
    def walk_on_windows(self):
        return self.store.value('walk_on_windows', False, type=bool)

    @walk_on_windows.setter
    def walk_on_windows(self, enabled):
        self.store.setValue('walk_on_windows', bool(enabled))
        self.store.sync()
