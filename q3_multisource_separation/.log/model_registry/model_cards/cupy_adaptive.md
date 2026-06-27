# CuPy Adaptive

- Model name: CuPy Adaptive
- Task type: Q3 close-frequency adaptive GPU backend
- Status: experimental
- Last updated: 2026-06-26
- Evidence: q3_experiment_results/d_cupy_adaptive_fallback_eps1e7_benchmark_18000/raw/q3_experiment_d_runtime.json

## Input Assumptions

- Repeated Monte Carlo or application samples share stable per-cell local frequency structure.
- A small pilot set can learn search centers without using the true center answer.

## Key Parameters

- `--compute-backend cupy_adaptive`
- `--adaptive-pilot-runs-per-cell 3`
- `--adaptive-audit-rate 0.05`
- `--adaptive-fallback-boundary-ratio 0.9`
- `--adaptive-audit-frequency-tolerance-hz 0.0005`

## Strengths

- Combines no-true-center pilot learning with fast learned-center GPU search and audit.

## Weaknesses

- Requires policy, fallback, and audit bookkeeping; first small runs may not amortize pilot cost.

## Failure Scenarios

- Pilot set is not representative of later samples.
- Future distributions shift enough that learned centers no longer cover the true local frequency region.
- Hard `Delta f=0.001 Hz` cases remain the dominant failure region.

## Runtime Cost

- 18,000 rows took 278.826 s with 96.04% success, 137 fallback rows, and 0/900 audit mismatches.

## Selection Guidance

- Use when: large repeated close-frequency workloads need no-true-center acceleration with audit evidence.
- Avoid when: every sample has unrelated frequency structure or no repeated cell-like grouping exists.

## Next Test

- Add policy reuse/load support and cell-level expansion only when audit mismatches appear.
