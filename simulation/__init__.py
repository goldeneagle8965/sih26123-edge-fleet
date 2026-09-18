"""SIH26123 — Edge-AI Distributed Fleet Coordination."""

from simulation.dashboard import Dashboard, serve
from simulation.engine import FleetSim
from simulation.metrics import RunMetrics, summarize_pair
from simulation.peer import PeerBus, PeerState
from simulation.robot import Robot
from simulation.world import Task, Warehouse

__all__ = [
    "Dashboard",
    "FleetSim",
    "PeerBus",
    "PeerState",
    "Robot",
    "RunMetrics",
    "Task",
    "Warehouse",
    "serve",
    "summarize_pair",
]
