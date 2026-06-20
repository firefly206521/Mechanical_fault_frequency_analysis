# 2026-06-20 Q4 Overnight Sensor Layout

## Purpose

- Validate the Q4 multisensor weighted GLRT layout model with large Monte Carlo runs across two machines.
- Check whether the selected three-sensor layout is stable across seed repeat, dense low-SNR sweep, strict false alarm, long observation window, and score-weight sensitivity.

## Setup

- Data: simulated multisensor signals using Q3 frequencies near 4, 8, 13, and 14 Hz.
- Models: single best sensor, random three-sensor layout, best three-sensor layout, all-sensors reference.
- Metrics: layout score, source-mean detection probability, low-SNR detection probability, empirical false alarm probability, balance variance, SNR performance.
- Run command: `python -m q4_sensor_layout.run_q4` through the overnight profile wrappers.
- Random seed: 20260619, 20260620, 20260621, 20260622, 20260623, 20260624.

## Results

- Winner: `bearing_left+gearbox_left+output_shaft` for the two standard 40 s baseline seeds and strict false alarm.
- Close alternatives: `bearing_left+bearing_right+gearbox_left` won low-SNR dense, long-window, and score-sensitivity profiles.
- Rejected models: single best sensor and random three-sensor layout are useful baselines but weaker in the low-SNR transition region.
- Empirical false alarm stayed near the requested level: about 0.04 to 0.05 for default profiles and about 0.01 for the strict false-alarm profile.
- Best-three fusion improves the transition-region score over single best and random three-sensor baselines, while all-sensors remains a useful upper reference rather than the deployable limit.

## Observed Pitfalls

- PC2 had two failed startup attempts before the successful baseline repeat; the final result directories are complete.
- The two best layouts are close enough that the paper should describe a primary recommendation plus a robustness alternative, not overclaim a unique global optimum.
- Output size is large; use `paper/` summaries for reporting and keep `raw/` only for traceability.

## Registry Updates

- Added `q4_weighted_glrt_sensor_fusion.md` as a selected model card.
- Rebuilt `model_index.csv`.

## Next Action

- Use `bearing_left+gearbox_left+output_shaft` as the main Q4 layout recommendation.
- In the conclusion, state that `bearing_left+bearing_right+gearbox_left` is an equivalent close candidate under low-SNR or long-window emphasis.
- If more testing is needed, focus only on sensitivity perturbation and correlated noise for these two top layouts.
