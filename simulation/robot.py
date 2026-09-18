"""Self-contained warehouse robot.

No central fleet scheduler. Task winners, paths, and right-of-way are computed here
from peer broadcasts this robot has actually received.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.config import (
    AUCTION_BATTERY_PENALTY,
    AUCTION_CONGESTION,
    AUCTION_WORKLOAD,
    BATTERY_START,
    BID_WINDOW,
    CHARGE_RATE,
    CHARGE_RESUME,
    CHARGE_THRESHOLD,
    DRAIN_MOVE,
    DRAIN_WAIT,
    DROP_TICKS,
    HOLD_HORIZON,
    LOOKAHEAD,
    PATH_HORIZON,
    PEER_STALE_TICKS,
    PICK_TICKS,
    STALEMATE_TICKS,
    UBPA_A,
    UBPA_B,
    UBPA_P,
    UBPA_U,
    UNREACHABLE_TICKS,
    YIELD_WAIT,
)
from simulation.peer import (
    MSG_BID,
    MSG_CLAIM,
    MSG_OBSTACLE,
    MSG_PEER_STATE,
    MSG_RELEASE,
    MSG_TASK_ANNOUNCE,
    MSG_YIELD_ACK,
    MSG_YIELD_NACK,
    MSG_YIELD_QUERY,
    PeerBus,
    PeerState,
)
from simulation.planner import (
    first_conflict,
    manhattan,
    nearest_cell,
    reservations_from_peers,
    spacetime_astar,
    spatial_path,
)
from simulation.world import Task, Warehouse

Pos = tuple[int, int]


@dataclass
class KnownTask:
    task_id: str
    pick: Pos
    drop: Pos
    urgency: float
    holder: str | None = None
    status: str = "OPEN"


@dataclass
class Auction:
    task_id: str
    opened_tick: int
    bids: dict[str, tuple[float, bool]] = field(default_factory=dict)
    closed: bool = False


@dataclass
class Negotiation:
    peer_id: str
    cell: Pos
    started: int
    my_score: float
    their_score: float | None = None
    decision: str | None = None  # KEEP, YIELD
    last_query: int = 0


class Robot:
    def __init__(
        self,
        robot_id: str,
        pos: Pos,
        world: Warehouse,
        bus: PeerBus,
        priority: int = 1,
        policy: str = "ubpa",
    ) -> None:
        self.id = robot_id
        self.pos = pos
        self.world = world
        self.bus = bus
        self.priority = priority
        self.policy = policy  # "ubpa" | "stop_wait"
        self.battery = BATTERY_START
        self.status = "IDLE"
        self.current_task: str | None = None
        self.task_urgency = 0.0
        self.planned_path: list[Pos] = [pos]
        self.velocity: tuple[int, int] = (0, 0)
        self.workload = 0
        self.tasks_done = 0
        self.known_tasks: dict[str, KnownTask] = {}
        self.peers: dict[str, PeerState] = {}
        self.known_blocked: set[Pos] = set()
        self.auctions: dict[str, Auction] = {}
        self.neg: Negotiation | None = None
        self.yield_wait_left = 0
        self.dwell = 0
        self.stuck_ticks = 0
        self.unreachable_ticks = 0
        self.wait_streak = 0
        self.deadlock_events = 0
        self.distance = 0.0
        self.wait_ticks = 0
        self.move_ticks = 0
        self.step_ms_sum = 0.0
        self.step_n = 0
        self.last_ubpa = 0.0
        self.goal: Pos | None = None
        self.phase = "IDLE"  # IDLE, TO_PICK, PICKING, TO_DROP, DROPPING, YIELDING, CHARGING
        self.resume_goal: Pos | None = None
        self.resume_phase: str | None = None
        self.yield_target: Pos | None = None
        self.events: list[dict[str, Any]] = []

    # ----- public step -------------------------------------------------

    def step(self, tick: int) -> Pos:
        import time

        t0 = time.perf_counter()
        self._ingest(tick)
        self._sense_and_share(tick)
        self._drop_stale_peers(tick)
        self._maybe_charge(tick)
        self._auction(tick)
        self._progress_task(tick)
        self._choose_goal()
        self._plan(tick)
        self._resolve_conflict(tick)
        intention = self._choose_move(tick)
        self._broadcast_state(tick)
        dt = (time.perf_counter() - t0) * 1000.0
        self.step_ms_sum += dt
        self.step_n += 1
        return intention

    def note_result(self, new_pos: Pos) -> None:
        old = self.pos
        moved = new_pos != old
        if moved:
            self.distance += manhattan(old, new_pos)
            self.move_ticks += 1
            self.velocity = (new_pos[0] - old[0], new_pos[1] - old[1])
            self.wait_streak = 0
            self.stuck_ticks = 0
            self.battery = max(0.0, self.battery - DRAIN_MOVE)
        else:
            self.wait_ticks += 1
            self.wait_streak += 1
            self.velocity = (0, 0)
            if self.phase == "CHARGING" and self.pos == self.world.charger:
                self.battery = min(100.0, self.battery + CHARGE_RATE)
            else:
                self.battery = max(0.0, self.battery - DRAIN_WAIT)
        self.pos = new_pos
        if self.planned_path and self.planned_path[0] == new_pos:
            pass
        elif self.planned_path:
            # snap path so index 0 is now
            if new_pos in self.planned_path:
                i = self.planned_path.index(new_pos)
                self.planned_path = self.planned_path[i:]
            else:
                self.planned_path = [new_pos] + [p for p in self.planned_path if p != new_pos]

    def peer_state(self, tick: int) -> PeerState:
        return PeerState(
            robot_id=self.id,
            position=self.pos,
            velocity=self.velocity,
            current_task=self.current_task,
            planned_path=list(self.planned_path[:PATH_HORIZON]),
            battery=self.battery,
            priority=self.priority,
            timestamp=tick,
            status=self.phase,
            task_urgency=self.task_urgency,
            workload=self.workload,
            ubpa_score=self.last_ubpa,
        )

    # ----- messages ----------------------------------------------------

    def _ingest(self, tick: int) -> None:
        for msg in self.bus.receive(self.id):
            kind = msg.get("type")
            if kind == MSG_PEER_STATE:
                ps = PeerState.from_msg(msg)
                if ps.robot_id != self.id:
                    self.peers[ps.robot_id] = ps
            elif kind == MSG_TASK_ANNOUNCE:
                self._note_task(msg)
            elif kind == MSG_BID:
                self._note_bid(msg, tick)
            elif kind == MSG_CLAIM:
                self._note_claim(msg)
            elif kind == MSG_RELEASE:
                self._note_release(msg, tick)
            elif kind == MSG_OBSTACLE:
                cell = msg.get("cell")
                if cell:
                    self.known_blocked.add((int(cell[0]), int(cell[1])))
            elif kind == MSG_YIELD_QUERY:
                self._on_yield_query(msg, tick)
            elif kind == MSG_YIELD_ACK:
                self._on_yield_ack(msg, tick)
            elif kind == MSG_YIELD_NACK:
                self._on_yield_nack(msg, tick)

    def _note_task(self, msg: dict[str, Any]) -> None:
        tid = str(msg["task_id"])
        pick = tuple(msg["pick"])
        drop = tuple(msg["drop"])
        urg = float(msg.get("urgency", 0.5))
        kt = self.known_tasks.get(tid) or KnownTask(tid, pick, drop, urg)
        kt.pick, kt.drop, kt.urgency = pick, drop, urg
        if kt.holder is None:
            kt.status = "OPEN"
        self.known_tasks[tid] = kt

    def _note_bid(self, msg: dict[str, Any], tick: int) -> None:
        tid = str(msg["task_id"])
        if tid not in self.known_tasks:
            self._note_task(msg)
        auc = self.auctions.get(tid)
        if auc is None or auc.closed:
            auc = Auction(tid, tick)
            self.auctions[tid] = auc
        cost = float(msg.get("cost", 1e9))
        valid = bool(msg.get("valid", False))
        auc.bids[str(msg.get("from_id"))] = (cost, valid)

    def _note_claim(self, msg: dict[str, Any]) -> None:
        tid = str(msg["task_id"])
        holder = str(msg.get("from_id"))
        if tid not in self.known_tasks:
            self._note_task(msg)
        kt = self.known_tasks[tid]
        kt.holder = holder
        kt.status = "CLAIMED"
        auc = self.auctions.get(tid)
        if auc:
            auc.closed = True
        if holder != self.id and self.current_task == tid:
            self.current_task = None
            self.task_urgency = 0.0
            self.phase = "IDLE"
            self.goal = None

    def _note_release(self, msg: dict[str, Any], tick: int) -> None:
        tid = str(msg["task_id"])
        if tid not in self.known_tasks:
            self._note_task(msg)
        kt = self.known_tasks[tid]
        if kt.status != "DONE":
            kt.holder = None
            kt.status = "OPEN"
            self.auctions[tid] = Auction(tid, tick)

    def _on_yield_query(self, msg: dict[str, Any], tick: int) -> None:
        if self.policy != "ubpa":
            return
        peer = str(msg.get("from_id"))
        cell = tuple(msg.get("cell") or self.pos)
        their = float(msg.get("score", 0.0))
        mine = self.ubpa_score(cell, int(msg.get("their_arrival", LOOKAHEAD)), tick)
        keep = self._i_keep_aisle(mine, their, peer)
        if keep:
            self._send(
                {
                    "type": MSG_YIELD_NACK,
                    "to_id": peer,
                    "score": mine,
                    "cell": list(cell),
                },
                tick,
            )
            if self.neg and self.neg.peer_id == peer:
                self.neg.decision = "KEEP"
                self.neg.their_score = their
        else:
            self._send(
                {
                    "type": MSG_YIELD_ACK,
                    "to_id": peer,
                    "score": mine,
                    "cell": list(cell),
                },
                tick,
            )
            self._begin_yield(peer, cell, mine, their, tick)

    def _on_yield_ack(self, msg: dict[str, Any], tick: int) -> None:
        # Peer yields. We keep the aisle.
        peer = str(msg.get("from_id"))
        if self.neg and self.neg.peer_id == peer:
            self.neg.decision = "KEEP"
            self.neg.their_score = float(msg.get("score", 0.0))
            self._event(tick, "ubpa_keep", f"{peer} ACKed, we keep aisle")

    def _on_yield_nack(self, msg: dict[str, Any], tick: int) -> None:
        # Peer keeps the aisle. We must yield.
        peer = str(msg.get("from_id"))
        cell = tuple(msg.get("cell") or self.pos)
        their = float(msg.get("score", 0.0))
        mine = self.last_ubpa
        self._begin_yield(peer, cell, mine, their, tick)
        self._event(tick, "ubpa_yield", f"{peer} NACKed, we yield")

    # ----- sensing / charging / tasks ---------------------------------

    def _sense_and_share(self, tick: int) -> None:
        seen = self.world.sense(self.pos)
        newly = seen - self.known_blocked
        self.known_blocked |= seen
        for cell in newly:
            self._send({"type": MSG_OBSTACLE, "cell": list(cell)}, tick)
            self._event(tick, "obstacle", f"sensed {cell}")
            if self.planned_path and cell in self.planned_path:
                self.planned_path = [self.pos]
                self.unreachable_ticks = 0

    def _drop_stale_peers(self, tick: int) -> None:
        stale = [
            rid
            for rid, p in self.peers.items()
            if tick - int(p.timestamp) > PEER_STALE_TICKS
        ]
        for rid in stale:
            del self.peers[rid]

    def _maybe_charge(self, tick: int) -> None:
        if self.current_task is not None:
            return
        if self.phase == "CHARGING":
            if self.battery >= CHARGE_RESUME:
                self.phase = "IDLE"
                self.goal = None
            else:
                self.goal = self.world.charger
            return
        if self.battery < CHARGE_THRESHOLD:
            self.phase = "CHARGING"
            self.goal = self.world.charger
            self._event(tick, "charge", "battery low, heading to charger")

    def _progress_task(self, tick: int) -> None:
        if not self.current_task:
            return
        kt = self.known_tasks.get(self.current_task)
        if kt is None:
            self.current_task = None
            self.phase = "IDLE"
            return
        if self.phase == "YIELDING":
            return
        if self.phase in ("IDLE",) and self.current_task:
            self.phase = "TO_PICK"
        if self.phase == "TO_PICK" and self.pos == kt.pick:
            self.phase = "PICKING"
            self.dwell = PICK_TICKS
        elif self.phase == "PICKING":
            self.dwell -= 1
            if self.dwell <= 0:
                self.phase = "TO_DROP"
                kt.status = "PICKED"
        elif self.phase == "TO_DROP" and self.pos == kt.drop:
            self.phase = "DROPPING"
            self.dwell = DROP_TICKS
        elif self.phase == "DROPPING":
            self.dwell -= 1
            if self.dwell <= 0:
                kt.status = "DONE"
                kt.holder = self.id
                self._send(
                    {
                        "type": MSG_CLAIM,
                        "task_id": kt.task_id,
                        "pick": list(kt.pick),
                        "drop": list(kt.drop),
                        "urgency": kt.urgency,
                        "done": True,
                    },
                    tick,
                )
                self._event(tick, "done", kt.task_id)
                self.current_task = None
                self.task_urgency = 0.0
                self.tasks_done += 1
                self.workload = self.tasks_done
                self.phase = "IDLE"
                self.goal = None
                self.planned_path = [self.pos]

    def _choose_goal(self) -> None:
        if self.phase == "YIELDING":
            self.goal = self.yield_target or self.goal
            return
        if self.phase == "CHARGING":
            self.goal = self.world.charger
            return
        if self.phase in ("PICKING", "DROPPING"):
            self.goal = self.pos
            return
        kt = self.known_tasks.get(self.current_task) if self.current_task else None
        if kt and self.phase in ("TO_PICK", "IDLE"):
            self.phase = "TO_PICK"
            self.goal = kt.pick
            self.task_urgency = kt.urgency
        elif kt and self.phase == "TO_DROP":
            self.goal = kt.drop
            self.task_urgency = kt.urgency
        elif not kt:
            self.goal = None

    # ----- auction -----------------------------------------------------

    def _auction(self, tick: int) -> None:
        if self.phase == "CHARGING":
            return
        if self.current_task is None and self.phase in ("IDLE", "TO_PICK"):
            for kt in self.known_tasks.values():
                if kt.status in ("OPEN", "RELEASED") and kt.holder is None:
                    self._ensure_bid(kt, tick)
        for tid, auc in list(self.auctions.items()):
            kt = self.known_tasks.get(tid)
            if auc.closed:
                if (
                    kt
                    and kt.holder is None
                    and kt.status not in ("DONE", "CLAIMED", "PICKED")
                    and self.current_task is None
                ):
                    auc.closed = False
                    auc.opened_tick = tick
                    auc.bids = {}
                continue
            if tick - auc.opened_tick < BID_WINDOW:
                continue
            winner = self._winner(auc)
            auc.closed = True
            if winner == self.id and self.current_task is None:
                self._claim(tid, tick)

    def _ensure_bid(self, kt: KnownTask, tick: int) -> None:
        auc = self.auctions.get(kt.task_id)
        if auc and (self.id in auc.bids) and not auc.closed:
            return
        if auc and auc.closed and kt.holder:
            return
        cost, valid = self._bid_cost(kt)
        if auc is None or auc.closed:
            auc = Auction(kt.task_id, tick)
            self.auctions[kt.task_id] = auc
        auc.bids[self.id] = (cost, valid)
        self._send(
            {
                "type": MSG_BID,
                "task_id": kt.task_id,
                "pick": list(kt.pick),
                "drop": list(kt.drop),
                "urgency": kt.urgency,
                "cost": cost,
                "valid": valid,
            },
            tick,
        )

    def _bid_cost(self, kt: KnownTask) -> tuple[float, bool]:
        d = manhattan(self.pos, kt.pick) + manhattan(kt.pick, kt.drop)
        cost = float(d)
        if self.battery < 30:
            cost += AUCTION_BATTERY_PENALTY
        overlap = 0
        probe = spatial_path(
            self.pos,
            kt.pick,
            self._blocked(),
            self.world.width,
            self.world.height,
        )
        probe += spatial_path(
            kt.pick,
            kt.drop,
            self._blocked(),
            self.world.width,
            self.world.height,
        )
        peer_cells: set[Pos] = set()
        for p in self.peers.values():
            peer_cells.update(tuple(c) for c in p.planned_path)
        overlap = sum(1 for c in probe if c in peer_cells)
        cost += AUCTION_CONGESTION * overlap
        cost += AUCTION_WORKLOAD * self.workload
        need = max(d, 1) * DRAIN_MOVE
        valid = self.battery >= need
        if not probe and d > 0:
            valid = False
            cost += 1000.0
        return cost, valid

    def _winner(self, auc: Auction) -> str | None:
        valid = [(rid, cost) for rid, (cost, ok) in auc.bids.items() if ok]
        if not valid:
            return None
        valid.sort(key=lambda t: (t[1], t[0]))
        return valid[0][0]

    def _claim(self, tid: str, tick: int) -> None:
        kt = self.known_tasks.get(tid)
        if kt is None or kt.holder not in (None, self.id):
            return
        kt.holder = self.id
        kt.status = "CLAIMED"
        self.current_task = tid
        self.task_urgency = kt.urgency
        self.phase = "TO_PICK"
        self.goal = kt.pick
        self._send(
            {
                "type": MSG_CLAIM,
                "task_id": tid,
                "pick": list(kt.pick),
                "drop": list(kt.drop),
                "urgency": kt.urgency,
            },
            tick,
        )
        self._event(tick, "claim", tid)

    def _release(self, reason: str, tick: int) -> None:
        tid = self.current_task
        if not tid:
            return
        kt = self.known_tasks.get(tid)
        if kt:
            kt.holder = None
            kt.status = "OPEN"
        self._send(
            {
                "type": MSG_RELEASE,
                "task_id": tid,
                "pick": list(kt.pick) if kt else [0, 0],
                "drop": list(kt.drop) if kt else [0, 0],
                "urgency": kt.urgency if kt else 0,
                "reason": reason,
            },
            tick,
        )
        self._event(tick, "release", f"{tid} {reason}")
        self.current_task = None
        self.task_urgency = 0.0
        self.phase = "IDLE"
        self.goal = None
        self.planned_path = [self.pos]
        self.unreachable_ticks = 0
        if kt:
            self.auctions[tid] = Auction(tid, tick)

    # ----- planning / conflict -----------------------------------------

    def _blocked(self) -> set[Pos]:
        return set(self.world.walls) | set(self.known_blocked)

    def _plan(self, tick: int) -> None:
        if self.phase in ("PICKING", "DROPPING"):
            self.planned_path = [self.pos]
            return
        goal = self.goal
        if goal is None:
            self.planned_path = [self.pos]
            return
        blocked = self._blocked()
        if self.policy == "stop_wait":
            # Naive baseline: shortest spatial path, no reservations, no wait-in-place.
            path = spatial_path(
                self.pos, goal, blocked, self.world.width, self.world.height
            )
        else:
            vres, eres = reservations_from_peers(self.peers, tick, HOLD_HORIZON)
            # do not reserve our own cell at t=now
            vres.discard((self.pos[0], self.pos[1], tick))
            path = spacetime_astar(
                self.pos,
                goal,
                blocked,
                self.world.width,
                self.world.height,
                vres,
                eres,
                tick,
                PATH_HORIZON,
            )
            if not path:
                path = spacetime_astar(
                    self.pos,
                    goal,
                    blocked,
                    self.world.width,
                    self.world.height,
                    set(),
                    set(),
                    tick,
                    PATH_HORIZON,
                )
        if not path:
            self.unreachable_ticks += 1
            self.planned_path = [self.pos]
            if self.current_task and self.unreachable_ticks >= UNREACHABLE_TICKS:
                self._release("unreachable", tick)
            return
        self.unreachable_ticks = 0
        self.planned_path = path[:PATH_HORIZON]

    def _conflict_peer(self) -> tuple[str, Pos, int] | None:
        mine = self.planned_path
        if len(mine) < 2:
            return None
        best: tuple[str, Pos, int] | None = None
        for rid, peer in self.peers.items():
            hit = first_conflict(mine, list(peer.planned_path or [peer.position]), LOOKAHEAD)
            if hit is None:
                continue
            idx, cell = hit
            if best is None or idx < best[2]:
                best = (rid, cell, idx)
        return best

    def ubpa_score(self, conflict_cell: Pos, my_arrival_idx: int, tick: int) -> float:
        arrival_bonus = max(0.0, (LOOKAHEAD - my_arrival_idx) / float(LOOKAHEAD))
        score = (
            UBPA_U * float(self.task_urgency)
            + UBPA_B * (self.battery / 100.0)
            + UBPA_P * float(self.priority)
            + UBPA_A * arrival_bonus
        )
        self.last_ubpa = score
        return score

    def _i_keep_aisle(self, mine: float, theirs: float, peer_id: str) -> bool:
        if abs(mine - theirs) < 1e-9:
            return self.id < peer_id
        return mine > theirs

    def _resolve_conflict(self, tick: int) -> None:
        hit = self._conflict_peer()
        if self.phase == "YIELDING":
            if self.yield_target and self.pos == self.yield_target:
                self.yield_wait_left -= 1
                if self.yield_wait_left <= 0:
                    self.phase = self.resume_phase or ("TO_PICK" if self.current_task else "IDLE")
                    self.goal = self.resume_goal
                    self.yield_target = None
                    self.neg = None
                    self._event(tick, "yield_done", "resuming")
            return
        if hit is None:
            if self.neg and tick - self.neg.started > 2:
                self.neg = None
            self.stuck_ticks = 0
            return

        peer_id, cell, idx = hit
        if self.policy == "stop_wait":
            # Keep the intended path so the peer still sees the head-on.
            # Movement is frozen in _choose_move.
            self.stuck_ticks += 1
            if self.stuck_ticks >= STALEMATE_TICKS and self.deadlock_events == 0:
                self.deadlock_events += 1
                self._event(tick, "deadlock", f"stop-and-wait vs {peer_id}")
            return

        mine = self.ubpa_score(cell, idx, tick)
        peer = self.peers.get(peer_id)
        their = None
        if peer and peer.ubpa_score is not None:
            their = float(peer.ubpa_score)
        if self.neg is None or self.neg.peer_id != peer_id:
            self.neg = Negotiation(peer_id, cell, tick, mine, their)
        self.neg.my_score = mine
        if their is not None:
            self.neg.their_score = their

        if self.neg.decision == "YIELD":
            return
        if self.neg.decision == "KEEP":
            return

        if tick - self.neg.last_query >= 2:
            self._send(
                {
                    "type": MSG_YIELD_QUERY,
                    "to_id": peer_id,
                    "score": mine,
                    "cell": list(cell),
                    "their_arrival": idx,
                },
                tick,
            )
            self.neg.last_query = tick

        # Local comparison if we already have their score (from PEER_STATE)
        if their is not None:
            if not self._i_keep_aisle(mine, their, peer_id):
                self._begin_yield(peer_id, cell, mine, their, tick)
                return

        if tick - self.neg.started >= STALEMATE_TICKS:
            # Safety net: smaller robot_id yields.
            if self.id > peer_id:
                self._begin_yield(peer_id, cell, mine, their or 0.0, tick)
                self._event(tick, "stalemate", f"id-break yield to {peer_id}")
            else:
                self.neg.decision = "KEEP"
                self._event(tick, "stalemate", f"id-break keep vs {peer_id}")

    def _begin_yield(
        self,
        peer_id: str,
        cell: Pos,
        mine: float,
        their: float,
        tick: int,
    ) -> None:
        if self.phase == "YIELDING":
            return
        self.neg = Negotiation(peer_id, cell, tick, mine, their, decision="YIELD")
        self.resume_goal = self.goal
        self.resume_phase = self.phase
        blocked = self._blocked()
        forbidden = {cell, self.pos}
        if self.planned_path:
            forbidden.update(self.planned_path[: max(2, LOOKAHEAD // 2)])
        target = nearest_cell(
            self.pos,
            self.world.turnouts,
            blocked,
            self.world.width,
            self.world.height,
            forbidden=forbidden,
        )
        if target is None:
            target = nearest_cell(
                self.pos,
                self.world.turnouts,
                blocked,
                self.world.width,
                self.world.height,
                forbidden={cell},
            )
        if target is None:
            # step backward if possible
            nbrs = [
                p
                for p in (
                    (self.pos[0] + dx, self.pos[1] + dy)
                    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
                )
                if p not in blocked and p != cell and self.world.in_bounds(p) and p not in self.world.walls
            ]
            target = nbrs[0] if nbrs else self.pos
        self.yield_target = target
        self.goal = target
        self.phase = "YIELDING"
        self.yield_wait_left = YIELD_WAIT
        self.last_ubpa = mine
        self._event(tick, "yield", f"to {target} vs {peer_id} score {mine:.2f}<{their:.2f}")

    def _peer_occupied(self) -> set[Pos]:
        """Cells peers currently occupy, from last-heard PEER_STATE only."""
        occupied: set[Pos] = set()
        for peer in self.peers.values():
            pos = getattr(peer, "position", None)
            if pos is not None:
                occupied.add(tuple(pos))
        return occupied

    def _choose_move(self, tick: int) -> Pos:
        if self.phase in ("PICKING", "DROPPING"):
            return self.pos
        if self.policy == "stop_wait" and self._conflict_peer() is not None:
            return self.pos
        if len(self.planned_path) >= 2:
            nxt = self.planned_path[1]
            if nxt in self._blocked() and nxt != self.pos:
                return self.pos
            # Rear-end / occupied-cell: do not step onto a peer's current cell.
            if nxt in self._peer_occupied():
                return self.pos
            return nxt
        return self.pos

    def _broadcast_state(self, tick: int) -> None:
        self.bus.broadcast(self.id, self.peer_state(tick).to_msg(), tick)

    def _send(self, msg: dict[str, Any], tick: int) -> None:
        self.bus.broadcast(self.id, msg, tick)

    def _event(self, tick: int, kind: str, detail: str) -> None:
        self.events.append({"tick": tick, "robot": self.id, "kind": kind, "detail": detail})
        if len(self.events) > 80:
            self.events = self.events[-80:]
