# Q4 V1 Implementation Log

## Scope

Implemented Q4 V1 as a separate adaptive sensor layout module. Q4 V0 code and overnight results were not modified.

## Model Summary

V1 uses a parameterized structural example instead of fixed named sensor positions. It generates dimensionless candidate surface points, each with a region label, coordinate, normal direction, noise level, and complex response to the four Q3/Q4 frequencies near 4, 8, 13, and 14 Hz.

The layout score is based on whitened response and the noncentral-parameter proxy:

```text
lambda_k(S) = A_k^2 h(S,k)^H Sigma(S)^-1 h(S,k)
```

The search prioritizes the weakest source, adds small information terms, and penalizes redundant whitened responses.

## Implementation

- Added `q4_adaptive_sensor_layout/`.
- Added CLI entrypoint: `python -m q4_adaptive_sensor_layout.run_q4_v1`.
- Added profiles: `smoke`, `medium`, and `official`.
- Added V1-only result directory: `q4_sensor_layout_v1_results/`.
- All generated files use the `q4_v1_` prefix.
- Paper-facing files are written under `paper/`; trace files are written under `raw/`.

## Validation

Commands run:

```powershell
python -m compileall q4_adaptive_sensor_layout
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile smoke
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium
python C:\Users\Firefly\.Codex\skills\paper-output-optimizer\scripts\check_result_tree.py q4_sensor_layout_v1_results
```

Medium result summary:

- `grid_size=96`
- `prescreen_count=40`
- exhaustive three-point combinations after prescreen: `9880`
- greedy + one-swap gap to exhaustive best: `0.0`
- medium runtime: about `13 s`
- official V1 result directory: `q4_sensor_layout_v1_results/`

## Known Limits

- V1 coordinates are dimensionless model coordinates, not true machine coordinates.
- The current propagation response is synthetic and parameterized; real deployment should replace it with finite-element or calibration-derived response matrices.
- At extremely low SNR, a maximum-response baseline can have higher average detection probability for strong faults, while V1 is optimized for weaker-source robustness and lower response redundancy.
- V1 should be treated as a method upgrade candidate until larger official validation is run.

