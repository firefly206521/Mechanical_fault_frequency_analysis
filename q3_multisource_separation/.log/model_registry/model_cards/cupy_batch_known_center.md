# CuPy Batch Known-Center

- Model name: CuPy Batch Known-Center
- Task type: Q3 close-frequency two-tone GPU fast kernel
- Status: experimental
- Last updated: 2026-06-26
- Evidence: q3_experiment_results/d_cupy_benchmark_1800/raw/q3_experiment_d_runtime.json

## Input Assumptions

- A reliable center frequency is supplied by the experiment or upstream detector.
- The problem is a close two-tone separation task around that center.

## Key Parameters

- `--compute-backend cupy_batch`
- `--cupy-center-span-hz`
- `--cupy-separation-min-hz`
- `--cupy-separation-max-hz`
- `--cupy-separation-step-hz`

## Strengths

- Extremely fast when the center prior is valid; 1,800 rows completed in 7.923 s in the recorded benchmark.

## Weaknesses

- Not a fair no-prior detector because it depends on a supplied center frequency.

## Failure Scenarios

- Center prior is wrong, absent, or not transferable across samples.
- The true signal is not a two-tone close-frequency pair.

## Runtime Cost

- Very low for large repeated workloads once the center prior is known.

## Selection Guidance

- Use when: an upstream full-auto, pilot, or domain model has already learned a trustworthy local center.
- Avoid when: evaluating a fully automatic detector with no center prior.

## Next Test

- Use as the fast path inside adaptive workflows, not as a standalone fairness baseline.
