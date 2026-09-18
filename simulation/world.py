"""Warehouse physics + WMS bulletin.

The World never assigns tasks, never plans paths, never decides who yields.
It only:
  - stores static walls and live blocked cells
  - moves robots that emit an intention
  - announces tasks as a broadcast (not an assignment)
  - counts collisions only for two robots claiming the same empty cell, or a swap
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.config import MAP_H, MAP_W, SENSOR_RANGE


@dataclass
class Task:
    task_id: str
    pick: tuple[int, int]
    drop: tuple[int, int]
    urgency: float
    announced_tick: int = 0
    holder: str | None = None
    status: str = "OPEN"  # OPEN, CLAIMED, PICKED, DONE, RELEASED
    complete_tick: int | None = None


@dataclass
class Warehouse:
    width: int = MAP_W
    height: int = MAP_H
    walls: set[tuple[int, int]] = field(default_factory=set)
    blocked: set[tuple[int, int]] = field(default_factory=set)
    turnouts: set[tuple[int, int]] = field(default_factory=set)
    depot: tuple[int, int] = (1, 1)
    charger: tuple[int, int] = (1, 9)
    robots: dict[str, tuple[int, int]] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)
    collision_events: int = 0
    collision_pairs: set[tuple[str, str, int]] = field(default_factory=set)

    def in_bounds(self, p: tuple[int, int]) -> bool:
        return 0 <= p[0] < self.width and 0 <= p[1] < self.height

    def static_blocked(self, p: tuple[int, int]) -> bool:
        return p in self.walls

    def is_free(self, p: tuple[int, int]) -> bool:
        return self.in_bounds(p) and p not in self.walls and p not in self.blocked

    def occupiable(self, p: tuple[int, int]) -> bool:
        return self.is_free(p)

    def neighbors(self, p: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = p
        out = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            q = (x + dx, y + dy)
            if self.is_free(q):
                out.append(q)
        return out

    def degree(self, p: tuple[int, int]) -> int:
        if not self.is_free(p):
            return 0
        return len(self.neighbors(p))

    def sense(self, pos: tuple[int, int], rng: int = SENSOR_RANGE) -> set[tuple[int, int]]:
        seen: set[tuple[int, int]] = set()
        px, py = pos
        for b in self.blocked:
            if abs(b[0] - px) + abs(b[1] - py) <= rng:
                seen.add(b)
        return seen

    def toggle_block(self, p: tuple[int, int]) -> bool:
        if not self.in_bounds(p) or p in self.walls:
            return False
        if p in self.blocked:
            self.blocked.discard(p)
            return False
        self.blocked.add(p)
        return True

    def set_block(self, p: tuple[int, int], on: bool) -> None:
        if not self.in_bounds(p) or p in self.walls:
            return
        if on:
            self.blocked.add(p)
        else:
            self.blocked.discard(p)

    def apply_moves(self, intentions: dict[str, tuple[int, int]], tick: int) -> dict[str, tuple[int, int]]:
        """Apply simultaneous moves.

        A collision is counted only when:
          - two robots claim the same currently-empty cell, or
          - two robots swap cells (A into B's cell and B into A's cell).
        Attempting to enter a cell a robot is staying in is a blocked step, not a collision.
        """
        current = dict(self.robots)
        dests: dict[str, tuple[int, int]] = {}
        for rid, dest in intentions.items():
            if not self.occupiable(dest) and dest != current.get(rid):
                dest = current[rid]
            dests[rid] = dest

        staying = {rid for rid, dest in dests.items() if dest == current[rid]}
        occupied_stay = {current[rid] for rid in staying}

        blocked: set[str] = set()
        rids = list(dests.keys())
        for i, a in enumerate(rids):
            for b in rids[i + 1 :]:
                if dests[a] == current[b] and dests[b] == current[a] and a != b:
                    pair = tuple(sorted((a, b)))
                    key = (pair[0], pair[1], tick)
                    if key not in self.collision_pairs:
                        self.collision_pairs.add(key)
                        self.collision_events += 1
                    blocked.add(a)
                    blocked.add(b)

        claimed: dict[tuple[int, int], str] = {}
        next_pos: dict[str, tuple[int, int]] = {}
        for rid, dest in dests.items():
            if rid in blocked:
                next_pos[rid] = current[rid]
                continue
            if dest == current[rid]:
                next_pos[rid] = dest
                continue
            if dest in occupied_stay:
                next_pos[rid] = current[rid]
                continue
            owner = claimed.get(dest)
            if owner is not None:
                pair = tuple(sorted((owner, rid)))
                key = (pair[0], pair[1], tick)
                if key not in self.collision_pairs:
                    self.collision_pairs.add(key)
                    self.collision_events += 1
                blocked.add(owner)
                blocked.add(rid)
                next_pos[owner] = current[owner]
                next_pos[rid] = current[rid]
            else:
                claimed[dest] = rid
                next_pos[rid] = dest

        for rid in blocked:
            next_pos[rid] = current[rid]
        for rid, pos in next_pos.items():
            self.robots[rid] = pos
        return dict(self.robots)

    def snapshot(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "walls": [list(p) for p in sorted(self.walls)],
            "blocked": [list(p) for p in sorted(self.blocked)],
            "turnouts": [list(p) for p in sorted(self.turnouts)],
            "depot": list(self.depot),
            "charger": list(self.charger),
            "tasks": [
                {
                    "task_id": t.task_id,
                    "pick": list(t.pick),
                    "drop": list(t.drop),
                    "urgency": t.urgency,
                    "holder": t.holder,
                    "status": t.status,
                    "complete_tick": t.complete_tick,
                }
                for t in self.tasks.values()
            ],
        }


def hyderabad_layout() -> Warehouse:
    """Narrow rack aisles, two east-west highways, depot and drop/charger.

    Inspired by a 3PL warehouse floor: racks occupy odd rows, 1-wide aisles
    between them, plus north and south highways for circulation.
    """
    w, h = MAP_W, MAP_H
    walls: set[tuple[int, int]] = set()
    for x in range(w):
        walls.add((x, 0))
        walls.add((x, h - 1))
    for y in range(h):
        walls.add((0, y))
        walls.add((w - 1, y))

    # Rack blocks on rows 3, 5, 7 with gaps (aisle mouths / turnouts)
    rack_rows = (3, 5, 7)
    gap_xs = {1, 2, 12, 13, 22, 23}
    for y in rack_rows:
        for x in range(1, w - 1):
            if x not in gap_xs:
                walls.add((x, y))

    # Keep depot/charger cells free
    walls.discard((1, 1))
    walls.discard((1, 9))
    walls.discard((2, 1))
    walls.discard((2, 9))

    wh = Warehouse(width=w, height=h, walls=walls, depot=(1, 1), charger=(1, 9))
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            p = (x, y)
            if p in walls:
                continue
            if wh.degree(p) >= 3:
                wh.turnouts.add(p)
    # Highway cells next to rack gaps also count as turnouts
    for x in (1, 2, 12, 13, 22, 23):
        for y in (2, 4, 6, 8):
            p = (x, y)
            if p not in walls:
                wh.turnouts.add(p)
    return wh


def default_tasks() -> list[Task]:
    """Six pick/drop jobs that force aisle traffic and a head-on on y=4."""
    return [
        Task("T1", pick=(4, 2), drop=(20, 8), urgency=0.9),
        Task("T2", pick=(20, 2), drop=(4, 8), urgency=0.85),
        Task("T3", pick=(8, 4), drop=(16, 6), urgency=0.7),
        Task("T4", pick=(16, 4), drop=(8, 6), urgency=0.65),
        Task("T5", pick=(6, 8), drop=(18, 2), urgency=0.55),
        Task("T6", pick=(18, 8), drop=(6, 2), urgency=0.5),
    ]


def spawn_positions() -> list[tuple[int, int]]:
    return [(2, 1), (12, 1), (22, 1), (2, 9)]
