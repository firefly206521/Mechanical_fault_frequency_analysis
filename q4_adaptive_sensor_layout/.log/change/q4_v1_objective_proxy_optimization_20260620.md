# Q4 V1 Objective Proxy Optimization - 2026-06-20

## Scope

- Optimized only the Q4 V1 adaptive sensor layout module.
- Did not modify Q1-Q3 or Q4 V0.
- Existing V0 authoritative results remain `q4_sensor_layout_results_overnight/`.

## Problem Found

The first V1 objective mixed small detection-strength terms with absolute, unitless redundancy and information-matrix terms. In the 10-minute official-style diagnostic, the selected `v1_adaptive_best` layout was not consistently better than the V0-like baseline:

- Old diagnostic output: `q4_sensor_layout_v1_results_10min_test/`
- Old `v1_adaptive_best`: `v1_p123+v1_p140+v1_p119`
- Average source detection: about `0.627`
- Low-SNR average source detection: about `0.460`
- Average weakest-source detection: about `0.462`
- Average empirical false alarm: about `0.048`

The root cause was that the analytic objective did not match the later fused GLRT detector closely enough.

## Changes

- Replaced the layout objective proxy with a fused GLRT detection proxy.
- Sensor responses are weighted by inverse noise variance before computing detection strength.
- Added `detection_min_lambda` and `detection_mean_lambda` to selected-layout CSV output.
- Scaled the redundancy and information-matrix terms by the detection-strength scale instead of letting them dominate the objective.
- Changed the default mean detection-strength weight to `0.10`, keeping the weakest-source term dominant.
- Made threshold calibration use the conservative `higher` quantile method.
- Added a regression test that verifies the new detection proxy fields are present and positive.
- Updated V1 README and report wording to describe the fused GLRT detection proxy.

## Commands Run

```powershell
python -m compileall q4_adaptive_sensor_layout
python -m pytest q4_adaptive_sensor_layout\tests -q
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium --output-dir q4_sensor_layout_v1_results_objective_proxy_medium --grid-size 120 --runs 100 --false-alarm-runs 200 --threshold-mc 180
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium --output-dir q4_sensor_layout_v1_results_objective_proxy_v2_medium --grid-size 120 --runs 100 --false-alarm-runs 200 --threshold-mc 180
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile official --output-dir q4_sensor_layout_v1_results_objective_proxy_v2_official_check --grid-size 160 --top-layouts 10 --runs 800 --false-alarm-runs 1600 --threshold-mc 800
python C:\Users\Firefly\.codex\skills\paper-output-optimizer\scripts\check_result_tree.py q4_sensor_layout_v1_results_objective_proxy_v2_official_check
```

## Validation Results

- Compile check passed.
- Unit tests passed: `6 passed`.
- Output tree check passed for `q4_sensor_layout_v1_results_objective_proxy_v2_official_check`.
- Official-check runtime: about `108.690 s`.
- Prescreen count: `40`; exhaustive combinations: `9880`.
- Greedy+swap gap to exhaustive best: about `0.061`.

## Official-Check Outcome

Best V1 layout after optimization:

- Layout: `v1_p105+v1_p074+v1_p140`
- Regions: `gearbox_zone_right+gearbox_zone_left+gearbox_zone_left`
- Average source detection: about `0.670`
- Low-SNR average source detection: about `0.506`
- Average weakest-source detection: about `0.574`
- Average empirical false alarm: about `0.039`

V0-like baseline in the same run:

- Layout: `v1_p074+v1_p119+v1_p141`
- Regions: `gearbox_zone_left+output_shaft_zone+gearbox_zone_right`
- Average source detection: about `0.663`
- Low-SNR average source detection: about `0.505`
- Average weakest-source detection: about `0.468`
- Average empirical false alarm: about `0.042`

The optimized V1 objective now selects a layout with similar average detection to the V0-like baseline, clearly better weakest-source balance, and no false-alarm increase.

## Known Limits

- The V1 coordinate system is still a parameterized structural example, not real equipment coordinates.
- The top V1 layouts cluster around gearbox-zone candidate points. This is acceptable for the current synthetic response field, but should be described as a model result rather than a physical installation prescription.
- Greedy+swap is close but not exact on the official-check grid; exhaustive search over the 40-point prescreen remains the trusted selector.

## Next Step

- Keep the optimized objective as the current V1 default.
- If further optimizing V1, focus on response-field realism and sensitivity perturbation rather than CPU parallelism; the official-check runtime is already under two minutes on this machine.
