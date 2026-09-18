# Evaluation

All numbers in `results/` come from `scripts/run_experiments.py`. The dashboard reads `results/metrics.json` if present; it never invents percentages.

Tick limit: 800. Improvement is `(baseline - ours) / baseline` **only when both policies finished**. Stop-and-wait never finished any experiment in this suite (`comparable=false`), so improvement % is `n/a` — not zero, not typed in.

## Experiments

| ID | Setup | What it answers |
|---|---|---|
| E1 | 3 robots, 6 tasks, 5 seeds, no extra blocks | throughput vs baseline |
| E2 | Forced head-on in a 1-wide aisle (3 seeds) | deadlock resolution |
| E3 | Aisle cell `(12, 4)` blocked at tick 16 (3 seeds) | reroute after a live obstacle |

E3 used to block `(8, 4)` at tick 40. By then that cell was already off remaining paths, so E3 matched E1. The current block sits on the rack-gap crossing while T1/T2/T3 still use it.

## Metrics

- `collision_count` — same-cell claims or 2-way swaps (not freeze-loop occupancy)
- `deadlock_count` — stalemate timeouts on the robot that is stuck
- `all_tasks_complete_tick` (or timeout)
- `mean_wait_ticks` — wait / (wait + move)
- `total_distance`
- `mean_comm_latency_ticks`
- `mean_robot_step_ms` — laptop clock proxy; varies run to run

## Measured (this machine, regenerated)

Source: `results/metrics.json`. Means across seeds. `mean_robot_step_ms` omitted here because it is a host-clock proxy, not a warehouse KPI.

### E1 — throughput

| metric | stop-and-wait | UBPA |
|---|---|---|
| finished | no (hit 800) | yes |
| complete tick | incomplete | 72 |
| tasks done | 0 / 6 | 6 / 6 |
| collisions | 2 | 2 |
| deadlocks | 2 | 0 |
| mean wait | 0.986 | 0.421 |
| distance | 34.0 | 125.0 |
| mean comm latency (ticks) | 1.998 | 1.976 |

### E2 — head-on aisle

| metric | stop-and-wait | UBPA |
|---|---|---|
| finished | no (hit 800) | yes |
| complete tick | incomplete | 51 |
| tasks done | 1 / 3 | 3 / 3 |
| collisions | 0 | 1 |
| deadlocks | 2 | 0 |
| mean wait | 0.992 | 0.654 |
| distance | 19.0 | 53.0 |
| mean comm latency (ticks) | 1.999 | 1.982 |

### E3 — mid-run aisle block

| metric | stop-and-wait | UBPA |
|---|---|---|
| finished | no (hit 800) | yes |
| complete tick | incomplete | 85 |
| tasks done | 3 / 6 | 6 / 6 |
| collisions | 0 | 0 |
| deadlocks | 3 | 0 |
| mean wait | 0.957 | 0.369 |
| distance | 104.0 | 161.0 |
| mean comm latency (ticks) | 1.998 | 1.979 |

## How to read this

Stop-and-wait is supposed to freeze on mutual path occupancy. That is why its distance is low and its wait fraction is ~1: robots barely move after the first conflict. UBPA travels farther because it finishes the jobs.

Do **not** claim “X% faster.” The baseline never produced a finish time, so the percentage formula does not apply.

Re-run after any planner/collision change:

```
python scripts/run_experiments.py
```
