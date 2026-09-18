# 3-minute demo script

**Setup:** `python scripts/run_demo.py` then open the printed URL.

0:00 — “Three warehouse AMRs. There is no central dispatcher. Each robot broadcasts pose, path, battery, task.”

0:20 — Point at the radio feed. “Robot A knows Robot B directly from this packet, not from a scheduler.”

0:40 — Tasks appear. “Auction: cost is distance + battery penalty + congestion + workload. Lowest valid bid wins. That is why R2 took task T3.”

1:10 — Head-on in the narrow aisle. “Conflict on planned paths. UBPA scores. The lower score yields into the turnout. Both continue. No one called a central lock.”

1:50 — Press **BLOCK AISLE** (or click a cell in front of a robot). “Local sensor range 2. Obstacle broadcast. Replan. If the pick is unreachable, the holder RELEASEs and peers re-auction.”

2:10 — Drag **packet loss** to ~40%. “Indoor radio is lossy. Dropped packets show in the counter. Stale peers do not freeze the aisle — stalemate timeout, lower id yields.”

2:20 — Metrics panel. “Same seeds, same map. Stop-and-wait never finishes (hits 800). UBPA finishes E1 in 72 ticks, E2 head-on in 51, E3 blocked aisle in 85. No improvement percentage — the baseline has no finish time.” Flip to **stop-and-wait** if there are 15 seconds left.

2:40 — Limitations: simulated radio, grid kinematics, laptop clock as edge CPU proxy.

## Judge questions

- “Who assigns tasks?” — Nobody. Each robot bids and independently checks who won.
- “Who has right of way?” — UBPA, then robot_id. Show the live scores.
- “What if both have stale data?” — Stalemate timeout, lower id yields.
