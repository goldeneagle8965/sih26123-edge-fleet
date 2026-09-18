"""Live spectator dashboard. Does not assign tasks or right-of-way."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulation.config import TICK_HZ  # noqa: E402
from simulation.dashboard import Dashboard, serve  # noqa: E402
from simulation.engine import FleetSim  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="SIH26123 live warehouse demo")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--policy", choices=("ubpa", "stop_wait"), default="ubpa")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--robots", type=int, default=3)
    args = p.parse_args()

    sim = FleetSim(n_robots=max(3, args.robots), policy=args.policy, seed=args.seed)
    dash = Dashboard(sim)
    httpd = serve(dash, args.host, args.port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://{args.host}:{args.port}/"
    print(f"SIH26123 dashboard: {url}")
    print("Click a cell to block it. Block aisle for the chaos beat.")
    print("Ctrl+C to stop.")
    interval = 1.0 / TICK_HZ
    try:
        while True:
            t0 = time.perf_counter()
            with dash.lock:
                sim.step()
            leftover = interval - (time.perf_counter() - t0)
            if leftover > 0:
                time.sleep(leftover)
    except KeyboardInterrupt:
        print("\nstopping")
        httpd.shutdown()


if __name__ == "__main__":
    main()
