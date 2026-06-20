# Q4 V1 Adaptive Sensor Layout

- Model name: Q4 V1 adaptive sensor layout with fused GLRT proxy
- Task type: Q4 parameterized sensor placement and multisensor weak-fault detection
- Status: experimental-selected
- Last updated: 2026-06-20
- Evidence: `q4_sensor_layout_v1_results_objective_proxy_v2_official_check/paper/q4_v1_selected_regions.csv`, `q4_sensor_layout_v1_results_objective_proxy_v2_official_check/paper/q4_v1_robust_detection.csv`, `q4_sensor_layout_v1_results_robustness_v2_medium/paper/q4_v1_validated_layouts.csv`, `q4_adaptive_sensor_layout/.log/change/q4_v1_objective_proxy_optimization_20260620.md`, `q4_adaptive_sensor_layout/.log/change/q4_v1_robustness_validation_outputs_20260620.md`

## Input Assumptions

- Candidate sensor positions are generated from a parameterized, dimensionless installable surface.
- Each candidate point has a region label, coordinate, installation normal, local noise scale, and complex response to the Q3 frequencies near 4, 8, 13, and 14 Hz.
- Coordinates are not real machine coordinates.
- The final validation detector is a weighted multisensor GLRT.

## Key Parameters

- Default profile set: `smoke`, `medium`, `official`.
- Default V1 objective: weakest-source fused GLRT detection proxy plus a small average-detection term.
- Default mean detection-strength weight: `0.10`.
- Redundancy and information-matrix terms are scaled by detection strength.
- Default target false alarm probability: `0.05`.
- Official-check command used grid size `160`, `800` signal runs per SNR, `1600` false-alarm runs per SNR, and `800` threshold Monte Carlo samples.
- Robustness controls include response gain jitter, response phase jitter, and equicorrelated sensor noise.

## Strengths

- Improves weakest-source balance over the V0-like regional baseline in the official-check run.
- Keeps false alarm near or below the requested 5% level after conservative threshold quantile calibration.
- Produces paper-facing and raw outputs in separated `paper/` and `raw/` directories with explicit `q4_v1_` file prefixes.
- The search can adapt to a denser candidate surface while preserving the Q1-Q3 GLRT modeling line.
- Adds a Monte Carlo validated ranking, so the analytic objective can reduce candidates while validation chooses the final reported layout.

## Weaknesses

- It is still a synthetic parameterized response field, not a measured or finite-element transfer-path model.
- The best V1 layout is sensitive to the response field; top layouts cluster around gearbox-zone candidates in the current example.
- Exhaustive search over the prescreened 40 points is still used as the trusted final selector because greedy+swap can miss the exact top layout.
- The analytic objective best can differ from the Monte Carlo validated best under response perturbation and correlated noise.
- The model is not yet a replacement for V0 in the paper mainline without additional robustness tests.

## Failure Scenarios

- Real equipment has a different transfer-path structure than the parameterized response field.
- Candidate points have correlated noise or common-mode disturbances not represented by the independent-noise simulation.
- The prescreen removes physically valuable low-response points that would help under a different noise or source scenario.
- The objective is tuned to weakest-source balance when the paper instead wants pure average detection probability.

## Runtime Cost

- Official-check run on this machine took about `109 s`.
- Medium diagnostics ran in about `12 s`.
- Robustness medium with response perturbation and correlated noise took about `42 s`.
- Current runtime does not justify CPU multiprocessing as the next priority.

## Selection Guidance

- Use as a V1 exploratory extension when the paper wants to show how the V0 finite-candidate layout can generalize to parameterized installable surfaces.
- Do not present the selected coordinates as real mechanical installation coordinates.
- Keep V0 as the validated baseline unless V1 receives additional perturbation and robustness evidence.
- Use `q4_v1_validated_layouts.csv` when choosing among V1 candidates after Monte Carlo validation.

## Next Test

- Run sensitivity-perturbation profiles on the response matrix to check whether the gearbox-zone cluster remains stable.
- Add a correlated-noise scenario if V1 is considered for the paper mainline.
