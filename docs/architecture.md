# Architecture

## What is centralized vs not

The **World** is physics + a simulated radio + a WMS bulletin that only *announces* tasks. It does not choose winners, paths, or who yields.

Each **Robot** is a self-contained agent:

```
sense nearby blocked cells
  → receive peer broadcasts + negotiation messages
  → update local peer table (drop stale)
  → auction / claim / release tasks locally
  → detect path conflicts vs peer planned_path
  → UBPA negotiate
  → space-time A* on local map
  → emit one move intention
  → broadcast PeerState
```

## Data flow

```
WMS bulletin (task announce)
        │  broadcast only
        ▼
Robot local cost  ── Bid ──►  Peer radio  ◄── Bid
        │                         │
        │              independent winner check
        ▼                         ▼
   Claim if I am lowest valid  Acknowledge
        │
        ▼
Local space-time planner using peer paths as reservations
        │
        ▼
Conflict? → YIELD_QUERY / ACK using UBPA scores
        │
        ▼
Yielding robot reverse-plans to nearest turnout, waits, resumes
```

## Message types

| Type | Who sends | Purpose |
|---|---|---|
| `PEER_STATE` | every robot, every tick | substrate |
| `TASK_ANNOUNCE` | WMS bulletin | new work, not an assignment |
| `BID` | idle/low-workload robots | auction |
| `CLAIM` | computed winner | I take it |
| `RELEASE` | current holder | unreachable / blocked |
| `OBSTACLE` | robot that sensed a block | map sharing |
| `YIELD_QUERY/ACK/NACK` | conflicting pair | negotiation |

## Deployment story

Student laptop today (this repo). Same `Robot.step()` on an edge Pi per AMR later; radio becomes UDP multicast. The dashboard is a spectator, not a controller.
