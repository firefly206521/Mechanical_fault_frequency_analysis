# 2026-06-20 Q3 Experiment C Order Calibration

## Purpose

- Close review issue #46 by measuring final model order after the complete Q3 GLRT-SIC-joint-refinement-BIC workflow.
- Replace the incomplete interpretation that treated the first-step GLRT pure-noise crossing rate as the final Q3 false-alarm rate.

## Setup

- Data: synthetic sinusoidal Monte Carlo, `N=40001`, `fs=100 Hz`, Gaussian noise `sigma=0.1`.
- Models: selected Q3 GLRT-SIC+BIC multisource separator.
- Metrics: final `P(K_hat>=1)` on K=0 noise, under/correct/over-estimation rates for K=1..4, weak-component detection and over-estimation in weak-strong mixtures.
- Run command: `python -m q3_multisource_separation.run_q3_experiment_c --profile official --workers 8 --output-dir q3_experiment_c_results`.
- Random seed: `SEED=20260620`.

## Results

- Winner: Q3 GLRT-SIC+BIC remains the selected Q3 method.
- K=0 final false alarm: `0/1000 = 0.000%`, Wilson 95% CI `[0.000%, 0.383%]`.
- Known-K calibration: K=1, 2, 3, 4 each had `500/500` correct final order selections.
- Weak-strong mixture: weak component detection was `65.5%`, `67.5%`, `68.0%`, and `69.5%` for weak-to-nearest-strong distances `0.5`, `1`, `2`, and `5 Hz`; over-estimation stayed at `0.0%`.

## Observed Pitfalls

- First-step GLRT and final workflow false alarm are different quantities; paper wording must name the final metric as `P(K_hat>=1)`.
- Weak-component misses are a real boundary, not a formatting issue. Strong-component over-estimation stayed controlled, but weak detection did not reach the well-separated known-K accuracy.

## Registry Updates

- Added `model_cards/q3_glrt_sic_bic_multisource.md`.
- Rebuilt `model_index.csv`.

## Next Action

- Use `q3_experiment_c_results/paper/q3_experiment_c_report.md` and its three summary CSVs when revising the Q3 paper section around final false alarm and order-selection reliability.
