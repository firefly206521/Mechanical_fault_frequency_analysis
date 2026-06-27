# 2026-06-26 Q3 Experiment D CuPy Adaptive 18000

## Purpose

- Validate whether adaptive pilot-calibrated GPU acceleration improves success rate and handles center-frequency misjudgment on an 18,000-row workload.

## Setup

- Data: synthetic Q3 Experiment D close-frequency two-tone grid.
- Models: `cupy_full_auto`, `cupy_batch`, `cupy_adaptive`.
- Metrics: success rate, runtime, fallback events, learned-center error, audit mismatch.
- Run command: `python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 400 --compute-backend cupy_adaptive ... --output-dir q3_experiment_results/d_cupy_adaptive_fallback_eps1e7_benchmark_18000`
- Random seed: project `SEED`.

## Results

- Winner: `cupy_adaptive` for no-true-center large repeated workloads.
- Close alternatives: `cupy_batch` is faster but requires a supplied or learned center; `cupy_full_auto` is the verifier.
- Rejected models: none; roles were separated rather than replacing one backend with another.

## Observed Pitfalls

- Known-center speedups must not be described as pure GPU acceleration.
- Success-rate changes must separate numeric boundary tolerance from algorithmic fallback.
- The dominant remaining hard cases are at `Delta f=0.001 Hz`.

## Registry Updates

- Added model cards for `CuPy Batch Known-Center`, `CuPy Full Auto`, and `CuPy Adaptive`.

## Next Action

- Add policy reuse/load support before the next large repeated run.
