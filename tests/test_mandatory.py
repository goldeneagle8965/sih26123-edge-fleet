"""Mandatory-requirement checks. No fabricated metrics."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulation.engine import FleetSim
from simulation.peer import MSG_PEER_STATE, MSG_YIELD_ACK, MSG_YIELD_NACK, MSG_YIELD_QUERY
from simulation.scenarios import head_on
from simulation.world import Task


SIM_DIR = ROOT / "simulation"


class TestForbiddenPatterns(unittest.TestCase):
    def test_no_central_scheduler(self) -> None:
        blob = "\n".join(p.read_text(encoding="utf-8") for p in SIM_DIR.glob("*.py"))
        self.assertNotIn("FleetScheduler", blob)
        self.assertNotIn("def resolve_deadlock", blob)

    def test_no_hardcoded_r1_winner(self) -> None:
        robot = (SIM_DIR / "robot.py").read_text(encoding="utf-8")
        tree = ast.parse(robot)
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                left = ast.unparse(node.left)
                rights = [ast.unparse(c) for c in node.comparators]
                combo = left + " ".join(rights)
                if "robot_id" in combo and '"R1"' in combo:
                    self.fail(f"hardcoded R1 comparison: {combo}")


class TestPeerBroadcast(unittest.TestCase):
    def test_three_robots_broadcast_schema(self) -> None:
        sim = FleetSim(n_robots=3, seed=1, announce_at=1000)
        for _ in range(6):
            sim.step()
        self.assertEqual(len(sim.robots), 3)
        required = {
            "robot_id",
            "position",
            "velocity",
            "current_task",
            "planned_path",
            "battery",
            "priority",
            "timestamp",
            "status",
            "task_urgency",
            "workload",
        }
        heard = 0
        for bot in sim.robots:
            for peer in bot.peers.values():
                msg = peer.to_msg()
                self.assertTrue(required.issubset(msg.keys()))
                heard += 1
        self.assertGreaterEqual(heard, 3)
        types = {e.get("type") for e in sim.bus.log}
        self.assertIn(MSG_PEER_STATE, types)


class TestAuction(unittest.TestCase):
    def test_lowest_valid_cost_claims(self) -> None:
        tasks = [Task("T1", pick=(4, 2), drop=(6, 2), urgency=0.8)]
        sim = FleetSim(
            n_robots=3,
            seed=1,
            tasks=tasks,
            spawn=[(2, 1), (22, 1), (12, 9)],
            announce_at=2,
        )
        holders = []
        for _ in range(40):
            sim.step()
            holders = [b.id for b in sim.robots if b.current_task == "T1"]
            if holders:
                break
        self.assertEqual(holders, ["R1"], "nearest robot with valid battery should win")
        self.assertIsNone(getattr(sim, "assign", None))


class TestNegotiation(unittest.TestCase):
    def test_head_on_ubpa_yields(self) -> None:
        sim = FleetSim(policy="ubpa", seed=1, announce_at=2, **head_on())
        kinds = []
        for _ in range(80):
            sim.step()
            kinds.extend(e["kind"] for e in sim.events)
        self.assertTrue(
            any(k in ("yield", "ubpa_yield", "ubpa_keep") for k in kinds),
            f"expected a yield/keep event, got {set(kinds)}",
        )
        radio = {e.get("type") for e in sim.bus.log}
        self.assertTrue(
            radio & {MSG_YIELD_QUERY, MSG_YIELD_ACK, MSG_YIELD_NACK},
            f"expected negotiation packets, got {radio}",
        )
        # Both aisle robots should have moved off their spawn after yielding/passing.
        r1, r2 = sim.robots[0], sim.robots[1]
        self.assertTrue(r1.pos != (4, 4) or r2.pos != (10, 4))

    def test_stop_wait_records_deadlock_on_head_on(self) -> None:
        sim = FleetSim(policy="stop_wait", seed=1, announce_at=2, **head_on())
        sim.run_until(60)
        self.assertGreater(sum(b.deadlock_events for b in sim.robots), 0)


class TestReplanAndReassign(unittest.TestCase):
    def test_block_triggers_obstacle_and_replan(self) -> None:
        sim = FleetSim(n_robots=3, seed=1, announce_at=2)
        for _ in range(25):
            sim.step()
        bot = next((b for b in sim.robots if len(b.planned_path) > 3), sim.robots[0])
        cell = bot.planned_path[min(3, len(bot.planned_path) - 1)]
        if cell == bot.pos:
            cell = (8, 4)
        before = list(bot.planned_path)
        sim.world.set_block(cell, True)
        for _ in range(8):
            sim.step()
        kinds = [e["kind"] for e in sim.events]
        self.assertIn("obstacle", kinds)
        self.assertTrue(
            bot.planned_path != before or cell in bot.known_blocked,
            "robot should sense the new block and replan or mark it",
        )

    def test_unreachable_pick_releases(self) -> None:
        tasks = [Task("T1", pick=(8, 4), drop=(16, 4), urgency=0.9)]
        sim = FleetSim(
            n_robots=3,
            seed=1,
            tasks=tasks,
            spawn=[(2, 4), (22, 1), (12, 9)],
            announce_at=2,
        )
        for _ in range(30):
            sim.step()
            if any(b.current_task == "T1" for b in sim.robots):
                break
        # Wall off the claimed pick so the holder cannot finish.
        for x in range(1, 24):
            if (x, 4) not in sim.world.walls:
                sim.world.set_block((x, 4), True)
        released = False
        for _ in range(40):
            sim.step()
            if any(e["kind"] == "release" for e in sim.events):
                released = True
                break
        self.assertTrue(released, "holder must RELEASE when the pick is walled off")


class TestMetrics(unittest.TestCase):
    def test_metrics_come_from_the_run(self) -> None:
        sim = FleetSim(n_robots=3, seed=1, announce_at=2)
        m = sim.run_until(30)
        d = m.to_dict()
        self.assertEqual(d["ticks"], sim.tick)
        self.assertEqual(d["collision_count"], sim.world.collision_events)
        self.assertEqual(d["tasks_total"], 6)
        self.assertGreater(d["mean_comm_latency_ticks"], 0)
        self.assertGreater(d["mean_robot_step_ms"], 0)


if __name__ == "__main__":
    unittest.main()
