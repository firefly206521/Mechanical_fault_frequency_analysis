# Q3 GLRT-SIC+BIC Multisource Separation

- Model name: Q3 GLRT-SIC+BIC multisource separation
- Task type: multi-source sinusoidal fault separation and automatic order selection
- Status: selected
- Last updated: 2026-06-20
- Evidence: `q3_multisource_separation_results_optimized_complete/`, `q3_experiment_c_results/`, `q3_experiment_d_results/`, `q3_multisource_separation/.log/change/q3_experiment_c_order_calibration_20260620.md`, `q3_multisource_separation/.log/change/q3_experiment_d_conditional_resolution_20260620.md`

## Input Assumptions

- Single-channel real-valued time series with weak sinusoidal components.
- Q3 synthetic calibration assumes `N=40001`, `fs=100 Hz`, Gaussian white noise, and candidate fault frequencies away from DC/Nyquist.
- Standard spaced-frequency calibration uses true frequencies in `[1, 15] Hz` with minimum separation at least `1 Hz`.
- Conditional close-frequency calibration in experiment D uses two tones centered at `5 Hz`, `T=400 s`, weak-component SNR levels `-6/-12/-18 dB`, amplitude ratios `1:1/1:3/1:10`, and random phases.

## Key Parameters

- Sequential residual GLRT with total false-alarm target `0.05` split over `max_components=10`, so one-step `p_fa=0.005`.
- GLRT threshold Monte Carlo count `500`.
- SIC candidate generation from residual GLRT peaks, followed by joint sinusoidal least-squares refinement.
- BIC acceptance threshold `Delta BIC=10`.
- Ill-conditioned fits are rejected when the design matrix condition number exceeds the Q3 reliability threshold.
- Experiment D used the complete detector with `max_components=4` and the same `Delta BIC=10`; close-pair-only output was kept out of the official result because it produced a non-monotonic initialization artifact at `Delta f=0.015 Hz`.

## Strengths

- Complete final-order calibration shows no final false alarm in `1000` K=0 trials: `P(K_hat>=1)=0.000%`, Wilson upper bound about `0.383%`.
- In well-separated synthetic data with `K=1..4`, `500` trials per K all selected the correct order.
- Conditional frequency MAE after correct order selection stayed around `2e-5 Hz`.
- The final BIC stage suppresses first-step GLRT false positives; paper text must distinguish these two rates.
- Experiment D replaces a single close-frequency limit with a conditioned surface. Under the tested `T=400 s` grid, the 90% empirical boundary was about `0.002 Hz` for `1:1`, `0.0025 Hz` for `1:3`, and `0.003 Hz` for `1:10`.

## Weaknesses

- Very weak components remain detection-limited: when one component has `A=0.005` and three components have `A=0.03-0.05` under `sigma=0.1`, weak detection was about `65.5%-69.5%`.
- The sequential candidate path can miss weak components before BIC has a chance to accept them.
- Resolution claims are conditional: SNR, amplitude ratio, phase distribution, record length, and success definition must be stated together.
- Runtime scales with repeated joint refinements and Monte Carlo validation, though the official experiment C run completed in about `439 s` with 8 CPU workers.

## Failure Scenarios

- Weak component buried under much stronger components.
- Very close or identical frequencies where the single-channel model becomes ill-conditioned or non-identifiable.
- Local close-pair-only diagnostics can produce isolated non-monotonic failures from initialization; use the complete detector for paper-level conditioned resolution curves.
- Structured, non-Gaussian, or colored residuals not represented by the white-noise calibration.

## Runtime Cost

- Experiment C official run: `1000` null trials, `4*500` known-K trials, and `4*200` weak-strong trials completed in about `438.6 s` with 8 workers.
- Experiment D official run: `3*3*10*200 = 18000` conditioned close-frequency trials completed in about `6243.3 s` with 8 workers.
- Null trials are cheap because most stop after the first GLRT scan; weak-strong trials are slower because several components are accepted and refined.

## Selection Guidance

- Use when Q3 needs interpretable multi-source sinusoidal separation with explicit final order selection.
- Use the complete-flow final false-alarm result for paper claims, not the first-step GLRT null scan alone.
- Use conditioned close-frequency curves for resolution claims; avoid writing any single number as a fixed theoretical limit.
- Avoid claiming reliable recovery of arbitrarily weak components; report weak-component detection as a boundary.

## Next Test

- If time allows, add colored-noise or off-center-frequency variants to test whether the conditioned resolution surface is stable outside the current white-noise, center-5-Hz setup.
