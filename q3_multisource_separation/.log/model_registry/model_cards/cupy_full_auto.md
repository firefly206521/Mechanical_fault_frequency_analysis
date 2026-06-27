# CuPy Full Auto

- Model name: CuPy Full Auto
- Task type: Q3 close-frequency two-tone GPU verifier
- Status: experimental
- Last updated: 2026-06-26
- Evidence: q3_experiment_results/d_cupy_full_auto_benchmark_1800/raw/q3_experiment_d_runtime.json

## Input Assumptions

- No true center frequency is supplied to the detector.
- A coarse FFT peak can provide a local search center per observation.

## Key Parameters

- `--compute-backend cupy_full_auto`
- `--cupy-auto-f-min-hz`
- `--cupy-auto-f-max-hz`
- `--cupy-auto-center-span-hz`
- `--cupy-auto-center-step-hz`

## Strengths

- Provides the no-true-center GPU oracle used by adaptive pilot, fallback, and audit.

## Weaknesses

- Local center/separation grid search is much slower than the known-center fast kernel.

## Failure Scenarios

- Very close, low-SNR cases can collapse to one-tone decisions or land on the frequency-error boundary.

## Runtime Cost

- 1,800 rows took 310.638 s in the recorded benchmark; projected 18,000-row full-auto runtime was about 52 minutes before adaptive acceleration.

## Selection Guidance

- Use when: validating adaptive fast paths or running no-prior correctness checks.
- Avoid when: a large repeated workload can amortize pilot learning and audit through `cupy_adaptive`.

## Next Test

- Keep as the verifier; optimize only if adaptive audit starts to dominate future workloads too heavily.
