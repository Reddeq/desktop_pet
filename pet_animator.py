from collections import deque
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, QTimer

from animation_graph import NODE_META, TRANSITIONS, find_path
from animation_node import AnimationNode
from pet_state import PetState


@dataclass
class AnimationStep:
    node: AnimationNode
    hold: bool = False


class PetAnimator(QObject):
    """
    Graph-driven аниматор.

    Отвечает за:
    - sequence из target nodes;
    - поиск путей по графу;
    - expanded queue;
    - interrupt / recovery;
    - переключение следующего шага по animation_finished / motion_complete.
    """

    def __init__(self, pet, animation_player, parent=None):
        super().__init__(parent)
        self.pet = pet
        self.animation_player = animation_player

        self.current_node: Optional[AnimationNode] = None
        self.current_step: Optional[AnimationStep] = None
        self.expanded_queue: deque[AnimationStep] = deque()

        self.is_interrupt_active: bool = False
        self.interrupt_node: Optional[AnimationNode] = None
        self.interrupt_recovery_targets: list[AnimationNode] = []

        self.bridge_timer = QTimer(self)
        self.bridge_timer.setSingleShot(True)
        self.bridge_timer.timeout.connect(self._on_bridge_timeout)

        # Небольшая пауза для "проходных" loop-поз
        self.bridge_hold_ms = 220

        # Временный compatibility layer для старых модулей,
        # пока весь стек ещё не переведён на чистые AnimationNode-сценарии.
        self.default_state_targets: dict[PetState, list[AnimationNode]] = {
            PetState.IDLE: [AnimationNode.SITTING_IDLE],
            PetState.WALK: [AnimationNode.WALKING],
            PetState.CLEANING: [AnimationNode.CLEANING],
            PetState.ALERT: [AnimationNode.ALERT],
            PetState.RUN: [AnimationNode.RUNNING],
            PetState.DIG: [AnimationNode.DIGGING],
            PetState.SWAT: [AnimationNode.SWATTING],
            PetState.SLEEP: [AnimationNode.SLEEPING],
        }

    # -------------------------
    # Public API
    # -------------------------

    def set_initial_node(self, node: AnimationNode):
        self.current_node = node
        self.current_step = AnimationStep(node=node, hold=True)
        self._play_node(node, force=True)

    def request_state(self, state: PetState, force: bool = False):
        """
        Временный bridge от старых PetState-вызовов.
        """
        if state == PetState.FALLING:
            self.interrupt_with(AnimationNode.FALLING)
            return

        if state == PetState.FALLING_RECOVERY:
            if self.is_interrupt_active and self.interrupt_node == AnimationNode.FALLING:
                self.resolve_interrupt()
            else:
                self.play_sequence_nodes(
                    [AnimationNode.FALLING_RECOVERY, AnimationNode.STANDING_IDLE],
                    replace=True,
                    force_restart=force,
                )
            return

        targets = self.default_state_targets.get(state)
        if not targets:
            return

        self.play_sequence_nodes(
            targets,
            replace=True,
            force_restart=force,
        )

    def play_sequence_nodes(
        self,
        target_sequence: list[AnimationNode],
        replace: bool = True,
        force_restart: bool = False,
    ):
        if not target_sequence:
            return

        if replace:
            self.expanded_queue.clear()
            self.bridge_timer.stop()

        start = self.current_node

        if start is None:
            first = target_sequence[0]
            first_hold = len(target_sequence) == 1
            self.current_node = first
            self.current_step = AnimationStep(node=first, hold=first_hold)
            self._play_node(first, force=True)

            if len(target_sequence) > 1:
                expanded = self._expand_targets(first, target_sequence[1:])
                self.expanded_queue.extend(expanded)
            return

        # SPECIAL CASE:
        # если просят force_restart того же самого единственного узла,
        # не строим путь по графу (он будет пустой), а просто заново проигрываем клип
        if (
            force_restart
            and len(target_sequence) == 1
            and self.current_node == target_sequence[0]
        ):
            node = target_sequence[0]
            meta = NODE_META[node]

            self.current_node = node
            self.current_step = AnimationStep(
                node=node,
                hold=(meta.loop or meta.requires_motion),
            )
            self._play_node(node, force=True)
            return

        if (
            not force_restart
            and len(target_sequence) == 1
            and self.current_node == target_sequence[0]
            and not self.is_interrupt_active
        ):
            return

        expanded = self._expand_targets(start, target_sequence)
        self.expanded_queue.extend(expanded)

        if self.current_step is None:
            self._advance_queue()
            return

        if force_restart:
            self._advance_queue()
            return

        if not self._is_currently_blocking_progress():
            self._advance_queue()

    def interrupt_with(
        self,
        node: AnimationNode,
        recovery_targets: Optional[list[AnimationNode]] = None,
    ):
        self.expanded_queue.clear()
        self.bridge_timer.stop()

        self.is_interrupt_active = True
        self.interrupt_node = node

        if recovery_targets is None:
            if node == AnimationNode.FALLING:
                recovery_targets = [
                    AnimationNode.FALLING_RECOVERY,
                    AnimationNode.STANDING_IDLE,
                ]
            else:
                recovery_targets = []

        self.interrupt_recovery_targets = recovery_targets

        self.current_node = node
        self.current_step = AnimationStep(node=node, hold=True)
        self._play_node(node, force=True)

    def resolve_interrupt(self):
        if not self.is_interrupt_active or self.interrupt_node is None:
            return

        recovery_targets = list(self.interrupt_recovery_targets)

        self.is_interrupt_active = False
        self.interrupt_node = None
        self.interrupt_recovery_targets = []

        if recovery_targets:
            self.play_sequence_nodes(
                recovery_targets,
                replace=True,
                force_restart=True,
            )

    def on_animation_finished(self, animation_name: str):
        try:
            finished_node = AnimationNode(animation_name)
        except ValueError:
            return

        if self.current_step is None:
            return

        if finished_node != self.current_step.node:
            return

        meta = NODE_META.get(finished_node)
        if meta is None:
            return

        if not meta.loop:
            self._advance_queue()

            # Если очередь была пуста и новый шаг не стартовал,
            # освобождаем current_step.
            if self.current_step is not None and self.current_step.node == finished_node:
                self.current_step = None

    def notify_motion_complete(self):
        if self.current_step is None:
            return

        meta = NODE_META.get(self.current_step.node)
        if meta is None:
            return

        if meta.requires_motion and not self.current_step.hold:
            self._advance_queue()

    def clear(self):
        self.expanded_queue.clear()
        self.bridge_timer.stop()
        self.current_step = None

    # -------------------------
    # Internal queue building
    # -------------------------

    def _expand_targets(
        self,
        start_node: AnimationNode,
        targets: list[AnimationNode],
    ) -> list[AnimationStep]:
        expanded_steps: list[AnimationStep] = []
        cursor = start_node
        total_targets = len(targets)

        for target_index, target in enumerate(targets):
            path = find_path(TRANSITIONS, cursor, target)
            if path is None:
                raise ValueError(f"No path from {cursor.value} to {target.value}")

            segment_nodes = path[1:]
            is_last_target = (target_index == total_targets - 1)

            for i, node in enumerate(segment_nodes):
                is_segment_target = (i == len(segment_nodes) - 1)
                meta = NODE_META[node]

                if is_segment_target and is_last_target:
                    hold = meta.loop or meta.requires_motion
                else:
                    hold = False

                expanded_steps.append(AnimationStep(node=node, hold=hold))

            cursor = target

        return expanded_steps

    # -------------------------
    # Internal playback
    # -------------------------

    def _advance_queue(self):
        if not self.expanded_queue:
            return

        next_step = self.expanded_queue.popleft()
        self.current_step = next_step
        self.current_node = next_step.node

        self._play_node(next_step.node, force=True)

        meta = NODE_META[next_step.node]

        # Если loop-узел используется как промежуточная "мостовая" поза,
        # продвигаем очередь коротким таймером.
        if meta.loop and not meta.requires_motion and not next_step.hold:
            self.bridge_timer.start(self.bridge_hold_ms)

    def _play_node(self, node: AnimationNode, force: bool = False):
        meta = NODE_META[node]
        self.animation_player.set_animation(
            node.value,
            loop=meta.loop,
            force=force,
        )

    def _on_bridge_timeout(self):
        if self.current_step is None:
            return

        meta = NODE_META[self.current_step.node]
        if meta.loop and not meta.requires_motion and not self.current_step.hold:
            self._advance_queue()

    def _is_currently_blocking_progress(self) -> bool:
        """
        Блокируют progression только:
        - one-shot узлы (пока не закончатся)
        - motion-узлы (пока не придёт notify_motion_complete)

        Обычные loop-позы считаем прерываемыми.
        """
        if self.current_step is None:
            return False

        meta = NODE_META[self.current_step.node]

        if not meta.loop:
            return True

        if meta.requires_motion:
            return True

        return False

    def force_set_node(self, node: AnimationNode, hold: bool = True):
        """
        Принудительно устанавливает текущий animation node,
        минуя поиск пути по графу.

        Нужен для специальных сценариев вроде:
        - hiding reveal после исчезновения за край экрана
        - других телепортирующихся / вне-графовых состояний
        """
        self.expanded_queue.clear()
        self.bridge_timer.stop()

        self.current_node = node
        self.current_step = AnimationStep(node=node, hold=hold)

        self._play_node(node, force=True)