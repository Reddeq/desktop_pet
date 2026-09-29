# Desktop Pet

Запуск: `python desktop_pet.py` (нужен PyQt6). Сборка Windows: `python build_release.py`.

## Как добавить поведение

Создайте один файл `pet_scenarios/<имя>.py` с классом, наследующим
`BehaviorScenario`. При запуске файлы этого каталога обнаруживаются
автоматически. Пример:

```python
from pet_scenarios import BehaviorScenario
from pet_state import PetState


class Stretch(BehaviorScenario):
    name = "stretch"       # уникальное имя
    weight = 0.05          # относительная вероятность выбора

    def can_start(self):
        return self.controller.needs.values.energy > 40

    def start(self):
        self.pet.set_state(PetState.IDLE)
```

Положительный `weight` включает сценарий в случайный выбор каждые пять
секунд, если питомец свободен. Веса относительны: добавление сценария
слегка меняет доли остальных. `priority = True` запускает сценарий
перед случайным выбором, когда `can_start()` вернул True. Для длительного
действия переопределите `is_busy()`, чтобы выбор не прерывал его;
`cancel()` вызывается при сбросе движения, `deactivate()` при остановке
контроллера. `on_animation_finished(name)` и `on_needs_tick()` доступны
для событий. Таймеры создавайте с родителем `self.controller` и
останавливайте в `cancel()/deactivate()`.

Можно использовать любую анимацию по имени: `self.pet.set_state("stretch")`.
Её PNG кадры кладутся в `assets/stretch/`; для невозобновляемой анимации
установите `self.pet.animation_player.loop_map["stretch"] = False` в
конструкторе сценария. При сборке `build_release.py` и `DesktopPet.spec`
включают все модули из `pet_scenarios`.

Существующие сценарии находятся в отдельных файлах каталога. Общие
механизмы физики, анимации и потребностей остаются в соответствующих
модулях; интерфейсные команды контроллера делегируют сценариям.
