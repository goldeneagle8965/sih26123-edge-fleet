# Optional features (after MVP)

- Charging policy when battery < 20%.
- More than three robots / larger map.
- Packet loss / radio delay slider — **in the live demo** (Operator panel). The scripted sweep is done: `scripts/run_degradation.py` writes `results/degradation.json` (clean, 40% loss, 70% loss, 3-tick delay, 40% loss + 3-tick delay; 5 seeds each).
- Export of judge-facing plots from `results/`.
- On-device (Raspberry Pi) tick loop — same robot code, real clock.
