# 2026-06-20 Q4 V1 Objective Proxy Optimization

## Purpose

- Check why the first Q4 V1 adaptive layout did not clearly beat the V0-like baseline.
- Align the analytic layout objective with the weighted GLRT Monte Carlo detector.
- Decide whether CPU optimization is needed before further model optimization.

## Setup

- Module: `q4_adaptive_sensor_layout/`
- Main output: `q4_sensor_layout_v1_results_objective_proxy_v2_official_check/`
- Frequencies: Q3/Q4 values near 4, 8, 13, and 14 Hz.
- Grid size: `160`
- Prescreen count: `40`
- Signal runs: `800` per SNR
- False-alarm runs: `1600` per SNR
- Threshold Monte Carlo samples: `800`
- SNR levels: `-25, -20, -15, -12, -10, -5 dB`

## Changes Tested

- Use fused GLRT detection proxy instead of unweighted summed response for layout scoring.
- Scale redundancy and information-matrix terms by detection strength.
- Set default mean detection-strength weight to `0.10`.
- Use conservative `higher` quantile threshold calibration.

## Results

- Best V1 layout: `v1_p105+v1_p074+v1_p140`.
- Best V1 regions: `gearbox_zone_right+gearbox_zone_left+gearbox_zone_left`.
- Average source detection: about `0.670`.
- Low-SNR average source detection: about `0.506`.
- Average weakest-source detection: about `0.574`.
- Average empirical false alarm: about `0.039`.
- V0-like regional baseline average source detection: about `0.663`.
- V0-like regional baseline average weakest-source detection: about `0.468`.
- V0-like regional baseline average empirical false alarm: about `0.042`.

## Decision

- Keep the fused GLRT detection proxy as the current V1 default.
- Do not prioritize CPU parallelism now; the official-check runtime is under two minutes.
- Treat V1 as an experimental-selected extension, not yet a replacement for V0's overnight-validated main result.

## Observed Pitfalls

- Absolute redundancy penalties can dominate detection terms because the detection proxy is around `1e-4`.
- An unscaled information-matrix term can also dominate the objective and select layouts for numerical conditioning rather than actual GLRT detection.
- Medium-size tests are useful for direction, but P_FA conclusions need more false-alarm trials.

## Registry Updates

- Added `q4_v1_adaptive_sensor_layout.md`.
- Rebuilt `model_index.csv`.

## Next Action

- If more time is available, test V1 under response-matrix perturbation and correlated noise.
- Keep generated raw results out of routine commits unless explicitly needed for submission packaging.
