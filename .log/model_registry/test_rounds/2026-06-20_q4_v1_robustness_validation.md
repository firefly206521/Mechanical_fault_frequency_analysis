# 2026-06-20 Q4 V1 Robustness Validation

## Purpose

- Verify that Q4 V1 can test response mismatch and correlated sensor noise without changing code.
- Add a Monte Carlo validated ranking because analytic objective rank and validation rank can diverge.

## Setup

- Module: `q4_adaptive_sensor_layout/`
- Main output: `q4_sensor_layout_v1_results_robustness_v2_medium/`
- Profile: `medium`
- Grid size: `120`
- Signal runs: `100` per SNR
- False-alarm runs: `300` per SNR
- Threshold Monte Carlo samples: `300`
- Response gain jitter: `0.15`
- Response phase jitter: `0.20`
- Sensor noise correlation: `0.30`

## Results

- Monte Carlo validated best: `v1_p105+v1_p074+v1_p062`.
- Validated best regions: `gearbox_zone_right+gearbox_zone_left+gearbox_zone_left`.
- Validation score: about `0.522`.
- Average source detection: about `0.619`.
- Low-SNR average source detection: about `0.437`.
- Average weakest-source detection: about `0.470`.
- Average empirical false alarm: about `0.052`.
- Analytic objective best: `v1_p105+v1_p074+v1_p098`.
- Analytic objective best validation rank: `5`.

## Decision

- Keep analytic objective as the candidate-reduction stage.
- Use `q4_v1_validated_layouts.csv` as the final V1 comparison surface after Monte Carlo.
- No CPU multiprocessing is needed yet; the robustness medium run took about `42 s`.

## Observed Pitfalls

- A layout with lower nominal false alarm can lose validation score if it gives up too much detection probability under perturbation.
- Robustness ranking depends on the validation-score formula, so the formula must be reported if used in paper-facing conclusions.

## Registry Updates

- Updated `q4_v1_adaptive_sensor_layout.md` with robustness controls and validated ranking guidance.
- Rebuilt `model_index.csv`.

## Next Action

- Only run a larger robustness official-check if V1 is promoted to the paper mainline.
- Otherwise, use V0 as the primary validated recommendation and V1 as a parameterized adaptive extension.
