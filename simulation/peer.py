"""Simulated radio. This is a broadcast medium, not a dispatcher.

Robots publish PeerState and negotiation messages. The bus delays/drops
packets and delivers copies into per-robot mailboxes. It never chooses
task winners, paths, or who yields.
"""

from __future__ import annotations

import random
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Any


MSG_PEER_STATE = "PEER_STATE"
MSG_TASK_ANNOUNCE = "TASK_ANNOUNCE"
MSG_BID = "BID"
MSG_CLAIM = "CLAIM"
MSG_RELEASE = "RELEASE"
MSG_OBSTACLE = "OBSTACLE"
MSG_YIELD_QUERY = "YIELD_QUERY"
MSG_YIELD_ACK = "YIELD_ACK"
MSG_YIELD_NACK = "YIELD_NACK"


@dataclass
class PeerState:
    robot_id: str
    position: tuple[int, int]
    velocity: tuple[int, int]
    current_task: str | None
    planned_path: list[tuple[int, int]]
    battery: float
    priority: int
    timestamp: int
    status: str
    task_urgency: float
    workload: int
    ubpa_score: float | None = None

    def to_msg(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = MSG_PEER_STATE
        d["from_id"] = self.robot_id
        return d

    @staticmethod
    def from_msg(msg: dict[str, Any]) -> "PeerState":
        path = [tuple(p) for p in msg.get("planned_path") or []]
        pos = msg.get("position") or (0, 0)
        vel = msg.get("velocity") or (0, 0)
        return PeerState(
            robot_id=str(msg["robot_id"]),
            position=(int(pos[0]), int(pos[1])),
            velocity=(int(vel[0]), int(vel[1])),
            current_task=msg.get("current_task"),
            planned_path=path,
            battery=float(msg.get("battery", 0)),
            priority=int(msg.get("priority", 1)),
            timestamp=int(msg.get("timestamp", 0)),
            status=str(msg.get("status", "IDLE")),
            task_urgency=float(msg.get("task_urgency", 0)),
            workload=int(msg.get("workload", 0)),
            ubpa_score=msg.get("ubpa_score"),
        )


@dataclass
class _InFlight:
    remaining: int
    dest: str
    msg: dict[str, Any]


@dataclass
class PeerBus:
    delay: int = 1
    drop_prob: float = 0.0
    rng: random.Random = field(default_factory=random.Random)
    subscribers: list[str] = field(default_factory=list)
    in_flight: list[_InFlight] = field(default_factory=list)
    mailboxes: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    log: deque = field(default_factory=lambda: deque(maxlen=250))
    delivered_count: int = 0
    dropped_count: int = 0
    latency_sum: float = 0.0
    latency_n: int = 0

    def register(self, robot_id: str) -> None:
        if robot_id not in self.subscribers:
            self.subscribers.append(robot_id)

    def broadcast(self, sender: str, msg: dict[str, Any], tick: int) -> None:
        packet = dict(msg)
        packet.setdefault("from_id", sender)
        packet["sent_tick"] = tick
        self.log.appendleft(
            {
                "tick": tick,
                "from_id": sender,
                "type": packet.get("type"),
                "task_id": packet.get("task_id"),
                "status": packet.get("status"),
                "to": packet.get("to_id"),
                "score": packet.get("score"),
            }
        )
        targets = [s for s in self.subscribers if s != sender]
        to_id = packet.get("to_id")
        if to_id:
            targets = [to_id] if to_id in self.subscribers and to_id != sender else []
        for dest in targets:
            if self.drop_prob > 0 and self.rng.random() < self.drop_prob:
                self.dropped_count += 1
                continue
            self.in_flight.append(_InFlight(self.delay, dest, dict(packet)))

    def tick(self, now: int) -> None:
        keep: list[_InFlight] = []
        for env in self.in_flight:
            if env.remaining <= 0:
                delivered = dict(env.msg)
                delivered["recv_tick"] = now
                sent = int(delivered.get("sent_tick", now))
                self.latency_sum += max(0, now - sent)
                self.latency_n += 1
                self.mailboxes[env.dest].append(delivered)
                self.delivered_count += 1
            else:
                env.remaining -= 1
                keep.append(env)
        self.in_flight = keep

    def receive(self, robot_id: str) -> list[dict[str, Any]]:
        msgs = self.mailboxes.get(robot_id, [])
        self.mailboxes[robot_id] = []
        return msgs

    def mean_latency(self) -> float:
        if self.latency_n == 0:
            return 0.0
        return self.latency_sum / self.latency_n

    def snapshot_log(self, n: int = 40) -> list[dict[str, Any]]:
        return list(self.log)[:n]
