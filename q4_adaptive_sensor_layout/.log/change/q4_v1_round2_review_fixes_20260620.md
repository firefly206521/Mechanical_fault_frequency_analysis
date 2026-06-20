# Q4 V1 Round 2 Review Fixes - 2026-06-20

## Scope

- Addressed the second review report: `q4_adaptive_sensor_layout/.log/review/code_review_round2_20260620.md`.
- Changed only the Q4 V1 adaptive sensor layout module and its tests/logs.
- Did not modify Q4 V0 or earlier questions.

## Fixes

- Exposed Monte Carlo validation-score weights in `Q4V1Config` and CLI:
  - `--validation-weight-pd`
  - `--validation-weight-low-snr`
  - `--validation-weight-min-pd`
  - `--validation-weight-fa-excess`
- Wrote validation-score weights to `raw/q4_v1_runtime.txt`, result README, and the paper-facing report.
- Extracted `fusion_weight_vector()` so analytic objective scoring and fused GLRT statistics share the same inverse-variance weighting logic.
- Changed response perturbation default from per `(sensor, fault)` element to per-sensor common jitter.
- Kept the stricter per-element perturbation as `--response-jitter-mode element`; default is `sensor`.
- Tightened the correlated-noise test by using a larger sample count and a stricter correlation threshold.
- Renamed layout and prescreen output column `mean_lambda` to `raw_mean_lambda`, clarifying that it is the unfused raw response average.

## Commands Run

```powershell
python -m compileall q4_adaptive_sensor_layout
python -m pytest q4_adaptive_sensor_layout\tests -q
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile smoke --output-dir q4_sensor_layout_v1_results_round2_fix_smoke --response-gain-jitter 0.10 --response-phase-jitter 0.10 --response-jitter-mode sensor --noise-correlation 0.20 --validation-weight-pd 0.45 --validation-weight-low-snr 0.35 --validation-weight-min-pd 0.20 --validation-weight-fa-excess -2.0
python C:\Users\Firefly\.codex\skills\paper-output-optimizer\scripts\check_result_tree.py q4_sensor_layout_v1_results_round2_fix_smoke
```

## Validation

- Compile check passed.
- Unit tests passed: `11 passed`.
- Smoke run completed in about `0.572 s`.
- Output tree check passed with `7` paper files and `4` raw files.
- Runtime file now records response jitter mode and validation-score weights.
- `q4_v1_selected_regions.csv` and `q4_v1_prescreen_scores.csv` now expose `raw_mean_lambda` rather than ambiguous `mean_lambda`.

## Review Item Status

- P1 validation-score hard-coded weights: fixed.
- P2 duplicated fusion weights: fixed.
- P2 per-element response jitter as default: fixed by defaulting to per-sensor jitter and adding a mode switch.
- P3 nondeterministic correlated-noise test: tightened.
- P3 `mean_lambda` semantic drift: fixed by renaming to `raw_mean_lambda`.

## Notes

- Existing result directories produced before this fix still contain the old column names and perturbation semantics. New result directories should be used for post-fix reporting.
- Larger medium/official reruns are only needed if V1 is promoted beyond an extension and becomes the main Q4 evidence path.
