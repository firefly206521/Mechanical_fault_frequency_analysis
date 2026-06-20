# Q4 V1 Adaptive Sensor Layout Results

This directory is the Q4 V1 result tree. All generated files use the `q4_v1_` prefix.

- `paper/` contains paper-facing V1 summaries, tables, figures, and report text.
- `raw/` contains V1 candidate points, prescreen scores, Monte Carlo trial rows, and runtime metadata.
- Q4 V0 authoritative overnight results remain in `q4_sensor_layout_results_overnight/`.

V1 is an adaptive layout optimization under a parameterized structural example. The coordinates are dimensionless model coordinates, not real-machine installation coordinates.

Run profile: `smoke`
Grid size: `36`
Random seed: `20260620`
Objective weights: detection_mean_lambda `0.1`, trace_info `0.002`, min_eigen `0.002`, scaled_redundancy `-0.03`
Robustness scenario: response_gain_jitter `0.1`, response_phase_jitter `0.1`, noise_correlation `0.2`
