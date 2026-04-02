from collections import deque
from dataclasses import dataclass

from animation_node import AnimationNode


@dataclass(frozen=True)
class NodeMeta:
    loop: bool
    requires_motion: bool = False


NODE_META: dict[AnimationNode, NodeMeta] = {
    AnimationNode.SITTING_IDLE: NodeMeta(loop=True),
    AnimationNode.WALKING: NodeMeta(loop=True, requires_motion=True),
    AnimationNode.SITTING_DOWN: NodeMeta(loop=False),
    AnimationNode.STANDING_UP: NodeMeta(loop=False),
    AnimationNode.RUNNING: NodeMeta(loop=True, requires_motion=True),
    AnimationNode.ALERT: NodeMeta(loop=False),
    AnimationNode.DIGGING: NodeMeta(loop=True),
    AnimationNode.CLEANING: NodeMeta(loop=True),
    AnimationNode.STANDING_IDLE: NodeMeta(loop=True),
    AnimationNode.SWATTING: NodeMeta(loop=True),
    AnimationNode.LAYING_DOWN: NodeMeta(loop=False),
    AnimationNode.SLEEPING: NodeMeta(loop=True),
    AnimationNode.SITTING_UP: NodeMeta(loop=False),
    AnimationNode.YAWNING: NodeMeta(loop=False),
    AnimationNode.MEOWING: NodeMeta(loop=False),
    AnimationNode.SCRATCHING_SCREEN: NodeMeta(loop=True),
    AnimationNode.EATING: NodeMeta(loop=False),
    AnimationNode.POOPING: NodeMeta(loop=False),
    AnimationNode.STARTLED: NodeMeta(loop=False),
    AnimationNode.HUNTING: NodeMeta(loop=True, requires_motion=True),
    AnimationNode.HIDING: NodeMeta(loop=True),
    # FALLING — interrupt, но как клип узел всё равно существует
    AnimationNode.FALLING: NodeMeta(loop=True),
    AnimationNode.FALLING_RECOVERY: NodeMeta(loop=False),
}


TRANSITIONS: dict[AnimationNode, list[AnimationNode]] = {
    AnimationNode.SITTING_IDLE: [
        AnimationNode.STANDING_UP,
        AnimationNode.MEOWING,
        AnimationNode.YAWNING,
        AnimationNode.ALERT,
        AnimationNode.EATING,
        AnimationNode.CLEANING,
        AnimationNode.SCRATCHING_SCREEN,
        AnimationNode.STARTLED,
        AnimationNode.LAYING_DOWN,
    ],

    AnimationNode.SLEEPING: [
        AnimationNode.SITTING_UP,
    ],

    AnimationNode.LAYING_DOWN: [
        AnimationNode.SLEEPING,
    ],

    AnimationNode.SITTING_UP: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.STARTLED: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.YAWNING: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.CLEANING: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.MEOWING: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.SITTING_DOWN: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.STANDING_UP: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.ALERT: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.EATING: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.SCRATCHING_SCREEN: [
        AnimationNode.SITTING_IDLE,
    ],

    AnimationNode.HIDING: [
        AnimationNode.FALLING,
    ],

    # falling в обычной логике не используется как путь из любого узла,
    # но recovery-путь как часть графа оставить полезно
    AnimationNode.FALLING: [
        AnimationNode.FALLING_RECOVERY,
    ],

    AnimationNode.FALLING_RECOVERY: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.POOPING: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.WALKING: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.DIGGING: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.RUNNING: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.HUNTING: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.SWATTING: [
        AnimationNode.STANDING_IDLE,
    ],

    AnimationNode.STANDING_IDLE: [
        AnimationNode.POOPING,
        AnimationNode.WALKING,
        AnimationNode.DIGGING,
        AnimationNode.RUNNING,
        AnimationNode.HUNTING,
        AnimationNode.SWATTING,
        AnimationNode.SITTING_DOWN,
    ],
}


def find_path(
    graph: dict[AnimationNode, list[AnimationNode]],
    start: AnimationNode,
    goal: AnimationNode,
) -> list[AnimationNode] | None:
    if start == goal:
        return [start]

    queue = deque([[start]])
    visited = {start}

    while queue:
        path = queue.popleft()
        node = path[-1]

        for nxt in graph.get(node, []):
            if nxt in visited:
                continue

            new_path = path + [nxt]
            if nxt == goal:
                return new_path

            visited.add(nxt)
            queue.append(new_path)

    return None