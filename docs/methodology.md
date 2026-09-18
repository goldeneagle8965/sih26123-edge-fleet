# Methodology

## Local planner

Space-time A* on a 4-connected grid. State = `(x, y, t)`. Actions: N/E/S/W/WAIT. Peer `planned_path[t]` cells are reserved. Unknown future: robots assumed to wait at last known cell for a short hold horizon.

## Auction cost

```
cost = dist(pos, pick) + dist(pick, drop)
     + 40  if battery < 30
     + 8 * overlapping_peer_path_cells
     + 6 * tasks_completed_this_run
```

Invalid if estimated remaining cells * drain > battery. Each robot computes this locally, broadcasts `BID`, waits `BID_WINDOW` ticks, then independently selects `argmin(valid bids)`. Equal cost: lexicographically smaller `robot_id` wins so every robot agrees without a referee.

## UBPA right-of-way (original contribution)

Higher score keeps the aisle. Lower score yields to the nearest turnout (intersection, degree ≥ 3).

```
score = 4.0 * task_urgency
      + 2.0 * (battery / 100)
      + 1.5 * priority
      + 1.0 * arrival_bonus
```

`arrival_bonus` is larger when the robot reaches the first conflicting cell sooner (already committed). Tie: smaller `robot_id` has right of way.

If scores would make both yield or neither (stale state), after `STALEMATE_TICKS` the smaller `robot_id` yields. That is the safety net, not the primary rule.

## Stop-and-wait baseline

Identical robots, auction, map, and tasks. Conflict policy: if any peer occupies a cell on my remaining path within `LOOKAHEAD`, stop. No yield, no reverse to turnout. Mutual waiting increments `deadlock_count` after the stalemate timeout and stays stuck until the other moves (which they may not).

## Sensing

A robot only *sees* a user-blocked cell within Manhattan distance `SENSOR_RANGE` (2). It then broadcasts `OBSTACLE`. Others do not magically know the block.
