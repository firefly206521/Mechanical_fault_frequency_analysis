# 2026-06-20 Q3 Experiment D Conditional Resolution Surface

## Purpose

- Replace a single Q3 close-frequency “resolution limit” with a conditioned empirical performance surface.
- Close review issue #47.

## Setup

- Data: synthetic two-tone close-frequency signals, `N=40001`, `fs=100 Hz`, `T=400 s`, center frequency `5 Hz`.
- Models: complete Q3 GLRT-SIC-joint-refinement-BIC detector.
- Metrics: success rate, Wilson 95% interval, 90% empirical resolution boundary, phase-bin success diagnostic.
- Run command: `python -m q3_multisource_separation.run_q3_experiment_d --profile official --workers 8 --output-dir q3_experiment_d_results`
- Random seed: `20260620`.

## Results

- Winner: complete Q3 detector; the close-pair-only diagnostic was rejected for this experiment because it produced a non-monotonic initialization artifact at `Delta f=0.015 Hz`.
- Close alternatives: none for the official result; `close_pair` remains a diagnostic CLI option.
- Rejected models: close-pair-only experiment output for the official paper surface.
- 90% empirical limits:
  - `1:1`: about `0.002 Hz`.
  - `1:3`: about `0.0025 Hz`.
  - `1:10`: about `0.003 Hz`.

## Observed Pitfalls

- A local near-frequency resolver can look better or worse for isolated grid points due to initialization, even when the full sequential detector behaves smoothly.
- The resolution boundary is conditional on SNR, amplitude ratio, phase distribution, record length, and the success definition.
- “Worst phase” from random trials should be reported as a phase-bin diagnostic, not a theoretical lower bound.

## Registry Updates

- Updated `q3_glrt_sic_bic_multisource.md` with experiment D evidence and conditional-resolution guidance.

## Next Action

- Use `q3_experiment_d_results/paper/q3_experiment_d_success_surface.png` and `q3_experiment_d_results/paper/q3_experiment_d_resolution_limits.csv` for paper-facing Q3 resolution discussion.
