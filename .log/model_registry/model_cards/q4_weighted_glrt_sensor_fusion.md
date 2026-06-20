# Q4 Weighted GLRT Sensor Fusion

- Model name: Weighted GLRT sensor fusion for robust sensor layout
- Task type: Q4 sensor layout and multisensor weak-fault detection
- Status: selected
- Last updated: 2026-06-20
- Evidence: `q4_sensor_layout_results_overnight/_summary/q4_overnight_job_summary.csv`, `q4_sensor_layout_results_overnight/_summary/q4_overnight_top_layouts.csv`, `q4_sensor_layout_results_overnight/_summary/q4_overnight_benchmark_snr.csv`

## Input Assumptions

- Candidate sensor positions are finite and named, not continuous physical coordinates.
- Fault frequencies and amplitudes use the Q3 final result: about 4, 8, 13, and 14 Hz.
- Each sensor has a sensitivity coefficient, propagation phase offset, and local noise scale.
- Detection is evaluated across balanced, spatially skewed noise, weak single sensor, and source-shadow scenarios.

## Key Parameters

- Fusion statistic: weighted sum of per-sensor GLRT statistics.
- Default target false alarm probability: 0.05; strict profile also tested 0.01.
- Default objective weights: `lambda_pfa=2.0`, `mu_balance=0.5`.
- Default observation window: 40 s; long-window profile uses 80 s.
- Overnight profiles used 180 to 300 Monte Carlo runs per SNR and 600 to 900 false-alarm runs.

## Strengths

- Consistently beats the single best sensor and random three-sensor baseline in the low-SNR transition region.
- The two best three-sensor layouts are stable across repeated seed, strict false alarm, long window, and score sensitivity profiles.
- Gives interpretable design guidance: include `gearbox_left`, add a bearing-side measurement, then choose `output_shaft` or the opposite bearing depending on robustness preference.
- Preserves a clear link to Q1-Q3 because the detector is still GLRT-based and uses Q3 frequencies.

## Weaknesses

- The best layout is not unique; `bearing_left+gearbox_left+output_shaft` and `bearing_left+bearing_right+gearbox_left` are close.
- Results are conditional on the abstract candidate-point sensitivity matrix, not a real finite-element or measured propagation model.
- Very low SNR below about -25 dB remains weak even with fusion.
- Full raw trial output is large, so paper materials should use summarized tables and keep raw CSVs only for traceability.

## Failure Scenarios

- Candidate sensitivity matrix is badly misspecified relative to real machinery.
- All available sensors have correlated noise or common-mode interference not represented in the simulation.
- One fault source is nearly invisible at all candidate positions.
- Two sources become physically inseparable before the Q3 frequency estimator can provide stable priors.

## Runtime Cost

- PC1 Anaconda runs took about 2.1 to 2.7 h per overnight job.
- PC2 Python 3.14 runs took about 11 to 20 min per comparable job.
- Long-window and strict false-alarm profiles increase cost through longer data or more null trials.

## Selection Guidance

- Use when: Q4 needs a defensible three-sensor layout under finite candidate positions and heterogeneous noise.
- Use `bearing_left+gearbox_left+output_shaft` as the conservative default because it won both standard 40 s baseline seeds and the strict false-alarm profile.
- Mention `bearing_left+bearing_right+gearbox_left` as the close robustness alternative because it won low-SNR dense, long-window, and score-sensitivity profiles.
- Avoid when: the problem requires physical coordinate optimization with real geometry and measured transfer paths.

## Next Test

- If time permits, run a targeted comparison only between the two top layouts under additional noise-correlation and sensitivity-perturbation profiles.
