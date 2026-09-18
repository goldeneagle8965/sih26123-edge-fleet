"""Named setups used by the live demo, experiments, and tests.

These are initial conditions only. Robots still auction, plan, and yield.
"""

from __future__ import annotations

from simulation.world import Task


def default_fleet() -> dict:
    return {"n_robots": 3, "tasks": None, "spawn": None}


def head_on() -> dict:
    """Two robots already sitting on 1-wide aisle y=4, facing each other.

    After a 2-tick pick they drive through each other unless someone yields.
    """
    tasks = [
        Task("T1", pick=(4, 4), drop=(10, 4), urgency=0.9),
        Task("T2", pick=(10, 4), drop=(4, 4), urgency=0.45),
        Task("T3", pick=(12, 8), drop=(22, 8), urgency=0.3),
    ]
    spawn = [(4, 4), (10, 4), (12, 1)]
    return {"n_robots": 3, "tasks": tasks, "spawn": spawn}


def blocked_aisle() -> dict:
    """Default jobs plus a mid-run block on the y=4 aisle.

    Tick 16 / cell (12, 4) is the rack-gap crossing while T1/T2/T3 still use it.
    Blocking (8, 4) at tick 40 is too late: that cell is already off remaining paths.
    """
    return {
        "n_robots": 3,
        "tasks": None,
        "spawn": None,
        "forced_block": (12, 4),
        "forced_block_tick": 16,
    }
