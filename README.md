# SIH26123 — Edge-AI Distributed Fleet Coordination

Three warehouse AMRs. No central dispatcher. Each robot broadcasts pose and path, auctions work, and yields with an explicit UBPA rule.

Python 3.10+, standard library only — no install step, no build step, no service to configure.

## Run it in one minute

```bash
git clone https://github.com/goldeneagle8965/sih26123-edge-fleet.git
cd sih26123-edge-fleet
python scripts/run_demo.py
```

Open the URL it prints (default <http://127.0.0.1:8765/>). That terminal *is* the simulation clock — 8 ticks/second. Leave it running and drive everything from the browser. `Ctrl+C` stops it.

No git? Use **Code → Download ZIP** on the repository page. The demo needs nothing but Python.

## The 60-second walkthrough

Work down the list in order; each beat builds on the one before it. All of it is live interaction, not a recorded clip.

| # | Do this | What you are seeing |
|---|---|---|
| 1 | Watch the first 20 seconds | Three AMRs with independent local plans. The **Radio (peer packets)** panel is the only channel between them — there is no dispatcher anywhere in the process. |
| 2 | Click any corridor cell | A live obstacle appears. The nearest robot re-plans around it; if that made a goal unreachable, the task goes back on the board and is re-auctioned. |
| 3 | Click **Block aisle** | Head-on conflict in a narrow corridor: conflict detection → local negotiation → one robot yields into a turnout → both continue with `deadlock_count` at 0. It is not collision-free: the run reports `collision_count` 2 and we print that number rather than hide it. |
| 4 | Drag **Packet loss** to 40% | Peer broadcasts start dropping and the `delivered · dropped` counter moves. Robots that miss a pose update wait rather than guess. Measured over 5 seeds: the same 6/6 tasks still finish, just later — 93–125 ticks instead of 72, with 0 deadlocks. |
| 5 | Drag **Radio delay** to 3 ticks | Intent arrives stale, so yields happen later. Measured: still 0 deadlocks, but only 3/6 tasks finish and intention conflicts rise to 577 — the honest failure mode, and the roadmap fix is age-filtering peer reservations. |
| 6 | Click **Policy: stop-and-wait** | Resets the same floor under the baseline. Two robots meet in the aisle, neither yields, `deadlock_count` climbs and `tasks_done` stalls — exactly the failure the UBPA rule exists to prevent. |
| 7 | Click **Policy: UBPA**, then **Pause** / **Reset** | Back to the fix. Pause freezes the clock so you can talk over a moment; Reset returns to the same seed. |

Two panels worth pointing at while this runs: **Live run meters** (this run only) and **Measured vs stop-and-wait** (loaded from `results/metrics.json`, never invented).

This list runs in the same order as the spoken version, so the timings carry over: `docs/demo_script.md` (0:00 → 2:40) and slide 10 of the deck (0:00 / 0:40 / 1:10 / 1:50 / 2:10 / 2:25).

Useful options:

```bash
python scripts/run_demo.py --policy stop_wait   # start in the baseline instead
python scripts/run_demo.py --port 9000          # port already in use
python scripts/run_demo.py --seed 7 --robots 4  # different layout draw
```

## Measure it yourself (about 4 seconds)

```bash
python scripts/run_experiments.py
```

Writes `results/metrics.json` and prints the comparison table. Fixed seeds mean re-running reproduces every decision metric exactly — tasks, ticks, deadlocks, collisions, distance, wait, comm latency. The only field that moves is `mean_robot_step_ms`, because that one is wall-clock on your machine.

Last measured run (tick limit 800; means across seeds):

| experiment | stop-and-wait | UBPA |
|---|---|---|
| E1 throughput | incomplete (0/6 tasks, 2 deadlocks) | **72 ticks, 6/6, 0 deadlocks** |
| E2 head-on | incomplete (1/3 tasks, 2 deadlocks) | **51 ticks, 3/3, 0 deadlocks** |
| E3 aisle block at t=16 | incomplete (3/6 tasks, 3 deadlocks) | **85 ticks, 6/6, 0 deadlocks** |

`improvement` is `null` throughout the JSON on purpose: the baseline never finished inside the tick limit, so every percentage would be meaningless (`comparable=false`). Raw values only. The full table, per-seed runs and the reasoning: `docs/evaluation.md`.

## Degrade the radio, then measure it

The two sliders in the Operator panel are not decoration: `scripts/run_degradation.py` sweeps packet loss and radio delay over 5 seeds each and writes `results/degradation.json`.

| scenario | UBPA outcome (means over 5 seeds) |
|---|---|
| clean (0% loss, 1 tick delay) | 6/6 tasks, 0 deadlocks, finishes tick 72 |
| 40% packet loss | **still 6/6, 0 deadlocks**, finishes in 93–125 ticks |
| 70% packet loss | only 1–5/6 tasks land — honest degradation |
| 3 tick radio delay | 0 deadlocks, but only 3/6 tasks: intention conflicts rise to 577 |
| 40% loss + 3 tick delay | still 6/6, finishes in 88–157 ticks |

40% loss is the number quoted in the decks and in the demo script, and it is read from this file at build time — never typed into a slide by hand.

## Tests

```bash
python -m unittest tests.test_mandatory
```

9 tests covering peer-broadcast schema, auction-winner validity, the two forbidden patterns (no central scheduler, no hardcoded winner), UBPA yielding, baseline deadlock recording, live block → replan, and unreachable-pick release. Expected: `Ran 9 tests ... OK`.

## Layout

```
simulation/   engine, robot, peer radio bus, space-time planner, UBPA rule, metrics, scenarios
frontend/     dashboard UI served by simulation/dashboard.py (stdlib http.server)
scripts/      run_demo.py, run_experiments.py, run_degradation.py, build_pptx.py
results/      metrics.json, degradation.json — measured, regenerated by scripts/
tests/        test_mandatory.py
docs/         problem analysis, requirements, architecture, methodology,
              measured evaluation, demo script, slide outline, both decks
```

Windows note: if `git` is not on your PATH, it lives at `C:\Program Files\Git\cmd\git.exe`.

## Presentation

Two decks, same measured numbers, different jobs:

- `docs/SIH26123_EdgeFleet_FULL-12slide-Detail.pptx` (and `.pdf`) — 12 slides, 16:9, speaker notes on all of them. Rebuild with `python scripts/build_pptx.py`.
- `docs/SIH26123_EdgeFleet_OFFICIAL-6slide-Template.pptx` (and the ready-to-upload `.pdf`) — the 6-slide official SIH format. Built from the supplied template by `../sih26123_pptbuild/build_tpl_26123.py`; see `../SIH26123_DECKS_README.md` for the deck-by-deck comparison.

Neither builder contains a typed metric. Both read `results/metrics.json` and `results/degradation.json` at build time, and `python ../sih26123_pptbuild/verify_deck_numbers_26123.py` re-reads both decks and fails (exit 1) if any cited number is missing from the results files or if an unexplained percentage appears.
