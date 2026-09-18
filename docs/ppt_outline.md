# 12-slide PPT outline (SIH26123)

1. **Hook:** What happens when 40 AMRs share one aisle and the 5G controller dies?
2. **Real problem:** Central WMS/fleet computers are a single point of delay and failure in Indian 3PL warehouses (narrow rack aisles, mixed human+robot traffic).
3. **Gap:** Stop-and-wait and central reservation scale poorly; they deadlock or wait on the cloud.
4. **Core idea:** Every robot is a planner + radio. Negotiate locally.
5. **Architecture:** Local planner ↔ peer broadcast ↔ conflict ↔ UBPA ↔ replan/re-auction. Dashboard is a spectator.
6. **Innovation:** UBPA right-of-way + turnout yield, not a token ring and not a central lock.
7. **Algorithm:** Auction cost; space-time A*; UBPA score; stalemate tie-break.
8. **India validation:** Hyderabad 3PL rack map (1-wide aisles, two highways, depot/drop).
9. **Results:** Show `results/metrics.json` / `docs/evaluation.md`. Stop-and-wait never finishes (hit 800); UBPA finishes E1 in 72, E2 in 51, E3 in 85. Do not invent a % improvement — `comparable=false`.
10. **Live demo:** Head-on + BLOCK AISLE + packet-loss slider + stop-and-wait contrast. Deck: `docs/SIH26123_Edge_Fleet_12_slides.pptx`.
11. **Deployment:** Laptop sim → Pi-per-robot UDP multicast → warehouse pilot.
12. **Line:** Robots that argue in the aisle do not wait for a control room.
