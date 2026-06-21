# Q3 Experiment D CPU Optimization Notes 2026-06-20

## Scope

- Branch: `codex/q3-experiment-d-cpu-optimization`.
- This is an experimental CPU-only optimization branch.
- `master` is not the target for these changes before another long-run need is explicitly approved.
- No official `--runs 200` experiment was started.

## Code Changes

- Added `--fit-backend dense|cached` to `run_q3_experiment_d.py`.
  - `cached` is now the experimental-branch default.
  - `dense` remains available as the exact fallback path.
- Added `--chunksize` for `ProcessPoolExecutor.map`.
  - Default remains `1` after short testing showed no benefit from `2`.
- Added `--timing-detail`.
  - Writes `raw/q3_experiment_d_timing_summary.csv`.
  - Writes `raw/q3_experiment_d_timing_summary.json`.
- Added optional grid subset controls for short validation:
  - `--snr-levels`
  - `--amplitude-ratios`
  - `--separations`
- Added a cached SSE objective in `core.py` to reduce repeated full design-matrix construction during frequency refinement.

## Validation Commands

```powershell
python -m compileall q3_multisource_separation

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --workers 1 --output-dir q3_experiment_results/d_opt_smoke_dense --fit-backend dense --timing-detail --snr-levels -6 --amplitude-ratios 1 --separations 0.002

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --workers 1 --output-dir q3_experiment_results/d_opt_smoke_cached --fit-backend cached --timing-detail --snr-levels -6 --amplitude-ratios 1 --separations 0.002

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --workers 1 --output-dir q3_experiment_results/d_opt_compare_dense --fit-backend dense --timing-detail --snr-levels -6 --amplitude-ratios 1 --separations 0.001,0.002,0.003

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --workers 1 --output-dir q3_experiment_results/d_opt_compare_cached --fit-backend cached --timing-detail --snr-levels -6 --amplitude-ratios 1 --separations 0.001,0.002,0.003

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 2 --workers 2 --chunksize 1 --output-dir q3_experiment_results/d_opt_chunksize_1 --fit-backend cached --timing-detail --snr-levels -6 --amplitude-ratios 1 --separations 0.001,0.002,0.003

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 2 --workers 2 --chunksize 2 --output-dir q3_experiment_results/d_opt_chunksize_2 --fit-backend cached --timing-detail --snr-levels -6 --amplitude-ratios 1 --separations 0.001,0.002,0.003
```

## Correctness Check

- Dense vs cached, single condition:
  - `success`: identical.
  - `estimated_k`: identical.
  - `ill_conditioned`: identical.
  - maximum frequency difference: `0.0 Hz`.
- Dense vs cached, three-separation subset:
  - all acceptance checks passed.
  - maximum frequency difference: `0.0 Hz`.

## Timing Snapshot

- Three-separation subset, single worker:
  - dense detector runtime sum: `3.636 s`.
  - cached detector runtime sum: `2.869 s`.
  - observed speedup on this tiny subset: about `1.27x`.
- Six-trial two-worker chunksize check:
  - `chunksize=1`: total runtime `6.386 s`, mean trial total `1.107 s`.
  - `chunksize=2`: total runtime `6.579 s`, mean trial total `1.130 s`.
  - conclusion: keep default `chunksize=1`.

## Medium Benefit Test

Command shape:

```powershell
python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --workers 8 --chunksize 1 --output-dir q3_experiment_results/d_opt_benefit_dense --fit-backend dense --timing-detail --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --workers 8 --chunksize 1 --output-dir q3_experiment_results/d_opt_benefit_cached --fit-backend cached --timing-detail --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004
```

Workload:

- 3 SNR levels.
- 3 amplitude ratios.
- 5 close-frequency separations.
- 8 Monte Carlo replicates.
- 360 trial rows per backend.

Correctness:

- `success`: all matched.
- `estimated_k`: all matched.
- `ill_conditioned`: all matched.
- maximum estimated-frequency difference: `0.0 Hz`.

Timing:

- dense wall time: `101.252 s`.
- cached wall time: `73.073 s`.
- wall-clock speedup: `1.386x`.
- wall-clock reduction: `27.83%`.
- dense detector total time: `767.020 s`, mean per trial `2.131 s`.
- cached detector total time: `540.743 s`, mean per trial `1.502 s`.
- detector-time speedup: `1.418x`.

## Limits

- These are smoke-scale checks, not replacement official results.
- Existing official results in `q3_experiment_results/d/` were not overwritten.
- Before using the cached backend for a new official run, run a medium subset with more SNR/ratio conditions and compare against dense again.
