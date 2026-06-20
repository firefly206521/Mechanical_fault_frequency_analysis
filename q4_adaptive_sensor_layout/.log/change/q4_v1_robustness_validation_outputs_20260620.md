# Q4 V1 Robustness Scenario and Validated Ranking - 2026-06-20

## Scope

- Extended Q4 V1 only.
- Added robustness simulation controls and a Monte Carlo validated layout ranking.
- Did not modify Q4 V0 or earlier questions.

## Changes

- Added CLI parameters:
  - `--response-gain-jitter`
  - `--response-phase-jitter`
  - `--noise-correlation`
- Added correlated sensor-noise generation for threshold calibration and noise trials.
- Added response perturbation for signal trials.
- Added `paper/q4_v1_validated_layouts.csv`.
- Added validation rank, validation score, and validated role columns to `paper/q4_v1_selected_regions.csv`.
- Updated the V1 report to show both the analytic objective best layout and the Monte Carlo validated best layout.
- Added unit tests for correlated noise and validated-rank scoring.

## Commands Run

```powershell
python -m compileall q4_adaptive_sensor_layout
python -m pytest q4_adaptive_sensor_layout\tests -q
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile smoke --output-dir q4_sensor_layout_v1_results_validation_smoke --response-gain-jitter 0.10 --response-phase-jitter 0.10 --noise-correlation 0.20
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium --output-dir q4_sensor_layout_v1_results_robustness_v2_medium --grid-size 120 --runs 100 --false-alarm-runs 300 --threshold-mc 300 --response-gain-jitter 0.15 --response-phase-jitter 0.20 --noise-correlation 0.30
python C:\Users\Firefly\.codex\skills\paper-output-optimizer\scripts\check_result_tree.py q4_sensor_layout_v1_results_robustness_v2_medium
```

## Validation Results

- Compile check passed.
- Unit tests passed: `9 passed`.
- Smoke output tree check passed with `7` paper files and `4` raw files.
- Robustness medium output tree check passed with `7` paper files and `4` raw files.
- Robustness medium runtime: about `41.608 s`.

## Robustness Medium Result

Scenario:

- response gain jitter: `0.15`
- response phase jitter: `0.20`
- sensor noise correlation: `0.30`

Monte Carlo validated best:

- Layout: `v1_p105+v1_p074+v1_p062`
- Regions: `gearbox_zone_right+gearbox_zone_left+gearbox_zone_left`
- Validation score: about `0.522`
- Average source detection: about `0.619`
- Low-SNR average source detection: about `0.437`
- Average weakest-source detection: about `0.470`
- Average empirical false alarm: about `0.052`

Analytic objective best in the same run:

- Layout: `v1_p105+v1_p074+v1_p098`
- Validation rank: `5`
- Validation score: about `0.493`
- Average empirical false alarm: about `0.029`

The analytic objective remains useful for candidate reduction, but the validated ranking is a better final selection surface when response perturbation and correlated noise are enabled.

## Known Limits

- The robustness scenario is still synthetic; it tests stability against model perturbation, not measured machine variability.
- The current validation score is a pragmatic scalar summary, not a theorem. It weights average detection, low-SNR detection, weakest-source balance, and false-alarm excess.
- If V1 becomes the paper mainline, the validation-score formula should be stated explicitly.

## Next Step

- Run a larger robustness official-check only if V1 is promoted over V0.
- Otherwise, keep V1 as an improved extension with clear nominal and perturbed-scenario evidence.
