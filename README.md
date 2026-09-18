# SIH26123 — Edge-AI Distributed Fleet Coordination

Three warehouse AMRs. No central dispatcher. Each robot broadcasts pose and path, auctions work, and yields with an explicit UBPA rule.

## Run the live demo

```
python scripts/run_demo.py
```

Open the printed URL (default http://127.0.0.1:8765/). Click a cell to block it, press **Block aisle**, or drag **packet loss / radio delay** to show a dying radio.

## Measure vs stop-and-wait

```
python scripts/run_experiments.py
```

Writes `results/metrics.json`. The dashboard reads that file; it does not invent percentages.

Last measured run (tick limit 800; means across seeds):

| experiment | stop-and-wait | UBPA |
|---|---|---|
| E1 throughput | incomplete (0/6 tasks, 2 deadlocks) | **72 ticks, 6/6, 0 deadlocks** |
| E2 head-on | incomplete (1/3 tasks, 2 deadlocks) | **51 ticks, 3/3, 0 deadlocks** |
| E3 aisle block at t=16 | incomplete (3/6 tasks, 3 deadlocks) | **85 ticks, 6/6, 0 deadlocks** |

Improvement % is `n/a` because the baseline never finished (`comparable=false`). Full table: `docs/evaluation.md`.

## Tests

```
python -m unittest tests.test_mandatory
```

Python 3.10+, stdlib only.
