from collections import deque
from dataclasses import dataclass

from animation_node import AnimationNode


@dataclass(frozen=True)
class NodeMeta:
    loop: bool
    requires_motion: bool = False


NODE_META: dict[AnimationNode, NodeMeta] = {
    AnimationNode.SIT_IDLE: NodeMeta(loop=True),
    AnimationNode.WALK: NodeMeta(loop=True, requires_motion=True),
    AnimationNode.SIT_DOWN: NodeMeta(loop=False),
    AnimationNode.STAND_UP: NodeMeta(loop=False),
    AnimationNode.RUN: NodeMeta(loop=True, requires_motion=True),
    AnimationNode.ALERT: NodeMeta(loop=False),
    AnimationNode.DIG: NodeMeta(loop=True),
    AnimationNode.START_DIG: NodeMeta(loop=False),
    AnimationNode.END_DIG: NodeMeta(loop=False),
    AnimationNode.CLEAN: NodeMeta(loop=True),
    AnimationNode.START_SANDBATH: NodeMeta(loop=False),
    AnimationNode.SANDBATH: NodeMeta(loop=True),
    AnimationNode.END_SANDBATH: NodeMeta(loop=False),
    AnimationNode.START_CLEAN: NodeMeta(loop=False),
    AnimationNode.END_CLEAN: NodeMeta(loop=False),
    AnimationNode.STAND_IDLE: NodeMeta(loop=True),
    AnimationNode.SWAT: NodeMeta(loop=False),
    AnimationNode.START_SHARPEN_CLAWS: NodeMeta(loop=False),
    AnimationNode.SHARPEN_CLAWS: NodeMeta(loop=True),
    AnimationNode.END_SHARPEN_CLAWS: NodeMeta(loop=False),
    AnimationNode.LIE_DOWN: NodeMeta(loop=False),
    AnimationNode.SLEEP: NodeMeta(loop=True),
    AnimationNode.SIT_UP: NodeMeta(loop=False),
    AnimationNode.YAWN: NodeMeta(loop=False),
    AnimationNode.MEOW: NodeMeta(loop=False),
    AnimationNode.SCRATCH_SCREEN: NodeMeta(loop=True),
    AnimationNode.START_SCRATCH_SCREEN: NodeMeta(loop=False),
    AnimationNode.END_SCRATCH_SCREEN: NodeMeta(loop=False),
    AnimationNode.EAT: NodeMeta(loop=True),
    AnimationNode.START_POOP: NodeMeta(loop=False),
    AnimationNode.POOP: NodeMeta(loop=True),
    AnimationNode.END_POOP: NodeMeta(loop=False),
    AnimationNode.STARTLE: NodeMeta(loop=False),
    AnimationNode.SNEAK: NodeMeta(loop=True, requires_motion=True),
    AnimationNode.START_SNEAK: NodeMeta(loop=False),
    AnimationNode.END_SNEAK: NodeMeta(loop=False),
    AnimationNode.JUMP: NodeMeta(loop=False),
    AnimationNode.HIDE: NodeMeta(loop=True),
    AnimationNode.START_HIDE: NodeMeta(loop=False),
    AnimationNode.END_HIDE: NodeMeta(loop=False),
    # FALL — interrupt, но как клип узел всё равно существует
    AnimationNode.DRAG: NodeMeta(loop=True),
    AnimationNode.FALL: NodeMeta(loop=False),
    AnimationNode.RECOVER: NodeMeta(loop=False),
}


TRANSITIONS: dict[AnimationNode, list[AnimationNode]] = {
    AnimationNode.SIT_IDLE: [
        AnimationNode.STAND_UP,
        AnimationNode.MEOW,
        AnimationNode.YAWN,
        AnimationNode.ALERT,
        AnimationNode.EAT,
        AnimationNode.START_CLEAN,
        AnimationNode.STARTLE,
        AnimationNode.LIE_DOWN,
    ],

    AnimationNode.SLEEP: [
        AnimationNode.SIT_UP,
    ],

    AnimationNode.LIE_DOWN: [
        AnimationNode.SLEEP,
    ],

    AnimationNode.SIT_UP: [
        AnimationNode.SIT_IDLE,
    ],

    AnimationNode.STARTLE: [
        AnimationNode.STAND_IDLE,
    ],

    AnimationNode.YAWN: [
        AnimationNode.SIT_IDLE,
    ],

    AnimationNode.START_CLEAN: [AnimationNode.CLEAN],
    AnimationNode.CLEAN: [AnimationNode.END_CLEAN],
    AnimationNode.END_CLEAN: [AnimationNode.SIT_IDLE],
    AnimationNode.START_SANDBATH: [AnimationNode.SANDBATH],
    AnimationNode.SANDBATH: [AnimationNode.END_SANDBATH],
    AnimationNode.END_SANDBATH: [AnimationNode.STAND_IDLE],

    AnimationNode.MEOW: [
        AnimationNode.SIT_IDLE,
    ],

    AnimationNode.SIT_DOWN: [
        AnimationNode.SIT_IDLE,
    ],

    AnimationNode.STAND_UP: [
        AnimationNode.STAND_IDLE,
    ],

    AnimationNode.ALERT: [
        AnimationNode.SIT_IDLE,
    ],

    AnimationNode.EAT: [
        AnimationNode.SIT_IDLE,
    ],

    AnimationNode.SCRATCH_SCREEN: [
        AnimationNode.END_SCRATCH_SCREEN,
    ],

    AnimationNode.START_SCRATCH_SCREEN: [AnimationNode.SCRATCH_SCREEN],
    AnimationNode.END_SCRATCH_SCREEN: [AnimationNode.STAND_IDLE],

    AnimationNode.START_HIDE: [AnimationNode.HIDE],

    AnimationNode.HIDE: [
        AnimationNode.END_HIDE,
    ],

    AnimationNode.END_HIDE: [
        AnimationNode.FALL,
    ],

    # fall в обычной логике не используется как путь из любого узла,
    # но recovery-путь как часть графа оставить полезно
    AnimationNode.FALL: [
        AnimationNode.RECOVER,
    ],
    AnimationNode.DRAG: [AnimationNode.FALL, AnimationNode.RECOVER],

    AnimationNode.RECOVER: [
        AnimationNode.STAND_IDLE,
    ],

    AnimationNode.START_POOP: [AnimationNode.POOP],
    AnimationNode.POOP: [AnimationNode.END_POOP],
    AnimationNode.END_POOP: [
        AnimationNode.STAND_IDLE,
    ],

    AnimationNode.WALK: [
        AnimationNode.STAND_IDLE,
    ],

    AnimationNode.START_DIG: [AnimationNode.DIG],
    AnimationNode.DIG: [AnimationNode.END_DIG],
    AnimationNode.END_DIG: [AnimationNode.STAND_IDLE],

    AnimationNode.RUN: [
        AnimationNode.STAND_IDLE,
    ],

    AnimationNode.START_SNEAK: [AnimationNode.SNEAK],
    AnimationNode.SNEAK: [AnimationNode.END_SNEAK],
    AnimationNode.END_SNEAK: [AnimationNode.STAND_IDLE],
    AnimationNode.JUMP: [AnimationNode.STAND_IDLE, AnimationNode.START_DIG],

    AnimationNode.SWAT: [
        AnimationNode.STAND_IDLE,
    ],
    AnimationNode.START_SHARPEN_CLAWS: [AnimationNode.SHARPEN_CLAWS],
    AnimationNode.SHARPEN_CLAWS: [AnimationNode.END_SHARPEN_CLAWS],
    AnimationNode.END_SHARPEN_CLAWS: [AnimationNode.STAND_IDLE],

    AnimationNode.STAND_IDLE: [
        AnimationNode.START_SANDBATH,
        AnimationNode.START_SHARPEN_CLAWS,
        AnimationNode.JUMP,
        AnimationNode.START_SCRATCH_SCREEN,
        AnimationNode.START_POOP,
        AnimationNode.WALK,
        AnimationNode.START_DIG,
        AnimationNode.RUN,
        AnimationNode.START_SNEAK,
        AnimationNode.SWAT,
        AnimationNode.SIT_DOWN,
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
