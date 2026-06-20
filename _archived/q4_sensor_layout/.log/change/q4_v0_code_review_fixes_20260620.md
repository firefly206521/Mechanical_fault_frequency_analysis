# Q4 V0 Code Review Fixes

## Scope

- Review source: `q4_sensor_layout/.log/review/q4_code_review_20260620.md`.
- Scope kept to Q4 V0 code quality and report correctness.
- No V1 propagation/grid model was introduced.

## Fixed

- Dynamic score formula in Markdown report:
  - `outputs.write_report()` now reads `lambda_pfa` and `mu_balance` from `Q4Config`.
  - Non-default runs such as `--lambda-pfa 3.5 --mu-balance 1.2` now render the correct formula.
- Fault coverage semantics:
  - `q4_fault_coverage.csv` now includes `scenario` and `scenario_count`.
  - Current V0 coverage rows are explicitly marked as `all_scenarios_mean`.
- Empty/boundary handling:
  - `write_report()` handles empty layout rankings without `IndexError`.
  - `benchmark_layout_names()` uses `next(..., None)` for optional single/three-sensor baselines.
  - `run_q4.py` rejects invalid `--runs`, `--threshold-mc`, and empty `--snr-levels`.
- Minor performance cleanup:
  - `coverage_rows` now uses the existing grouped dictionary instead of repeatedly scanning all detection rows.
  - Sensor name to index mapping is now module-level.
  - Time axis and sine/cosine bases are precomputed once per experiment and passed into trial evaluation.
- CSV writer reuse:
  - Added `q4_sensor_layout/_io.py`.
  - `outputs.py` and `summarize_overnight.py` now share `write_csv()`.
- Score-weight interpretation:
  - The report now explains that false-alarm penalty is an empirical safety term; the main false-alarm control still comes from threshold calibration.

## Validation

```text
python -m compileall q4_sensor_layout
python -m q4_sensor_layout.run_q4 --output-dir q4_sensor_layout_results_review_fix_smoke --runs 1 --false-alarm-runs 1 --threshold-mc 5 --duration-s 2 --snr-levels -20 --scenarios balanced --seed 20260620
python -m q4_sensor_layout.run_q4 --output-dir q4_sensor_layout_results_review_fix_smoke_custom --runs 1 --false-alarm-runs 1 --threshold-mc 5 --duration-s 2 --snr-levels -20 --scenarios balanced --seed 20260620 --lambda-pfa 3.5 --mu-balance 1.2
python -m q4_sensor_layout.summarize_overnight --root-output q4_sensor_layout_results_overnight
python C:\Users\Firefly\.codex\skills\paper-output-optimizer\scripts\check_result_tree.py E:\AIworkspace\2026CSU-math\testA\q4_sensor_layout_results_review_fix_smoke
```

## Notes

- Existing overnight raw Monte Carlo data was not regenerated.
- `summarize_overnight` was rerun and refreshed `_summary` from the existing overnight job directories.
