# Q4 V0 Stage Closeout

## Scope

- Close out Q4 V0 before starting a separate V1 branch.
- V0 scope is finite candidate-region sensor layout, weighted GLRT fusion, and Monte Carlo robustness validation.
- No algorithm changes and no additional large experiments were run during this closeout.

## Current Authoritative Results

- Source module: `q4_sensor_layout/`
- Light/default result directory: `q4_sensor_layout_results/`
- Authoritative overnight result directory: `q4_sensor_layout_results_overnight/`
- Overnight summary directory: `q4_sensor_layout_results_overnight/_summary/`

The authoritative V0 conclusion should be based on the overnight summaries, not the earlier light run.

## Model and Parameters

- Observation model:

  \[
  y_m(t)=\sum_k h_{mk}A_k\sin(2\pi f_kt+\phi_k+\delta_{mk})+n_m(t).
  \]

- Fusion statistic:

  \[
  T_{\mathrm{fused}}(f)=\sum_{m\in S}w_mT_m(f),\qquad w_m\propto 1/\hat\sigma_m^2.
  \]

- Score:

  \[
  J(S)=\overline{P_D(S)}-\lambda P_{FA}(S)-\mu\operatorname{Var}_k(P_{D,k}(S)).
  \]

- Default parameters:
  - `p_fa=0.05`
  - `lambda_pfa=2.0`
  - `mu_balance=0.5`
  - `fs=100 Hz`
  - default duration `40 s`
  - Q3 frequencies approximately `4, 8, 13, 14 Hz`

## Commands

```text
.\q4_sensor_layout\run_overnight_pc1.ps1
.\q4_sensor_layout\run_overnight_pc2.ps1
python -m q4_sensor_layout.summarize_overnight --root-output q4_sensor_layout_results_overnight
```

## Key Results

- Standard 40 s baseline seed 20260619 winner: `bearing_left+gearbox_left+output_shaft`.
- Standard 40 s baseline repeat seed 20260620 winner: `bearing_left+gearbox_left+output_shaft`.
- Strict false-alarm profile winner: `bearing_left+gearbox_left+output_shaft`, empirical mean false alarm about `0.0096`.
- Low-SNR dense, long-window, and score-sensitivity profiles winner: `bearing_left+bearing_right+gearbox_left`.
- V0 paper recommendation:
  - main layout: `bearing_left+gearbox_left+output_shaft`
  - close robustness alternative: `bearing_left+bearing_right+gearbox_left`

The two layouts are close enough that the paper should not overclaim a unique physical optimum.

## Validation

- Real-data link: Q4 uses the Q3 detected frequencies and amplitudes as source parameters.
- Synthetic validation: multisensor signals are generated under sensitivity, phase-offset, and noise-field scenarios.
- SNR sweep: standard profiles cover `-25, -20, -15, -12, -10, -5 dB`; dense low-SNR profile covers `-30` to `-15 dB`.
- False alarm: default profiles use `P_FA=0.05`; strict profile uses `P_FA=0.01`.
- Edge/stress scenarios:
  - balanced
  - spatial noise skew
  - weak single sensor
  - source shadow

## Known Limits

- V0 is a finite candidate-region model. It does not compute continuous physical coordinates on an unknown machine.
- Candidate names are abstract installable regions under assumed sensitivity/noise matrices.
- The current model assumes independent sensor noise after local scaling; correlated spatial noise belongs in a future V1 or sensitivity extension.
- Without geometry, material, and measured transfer paths, the result is a robust strategy under assumptions, not a universal real-device coordinate solution.

## Files Produced

- Paper-facing:
  - `q4_sensor_layout_results_overnight/*/*/paper/q4_report.md`
  - `q4_sensor_layout_results_overnight/*/*/paper/q4_layout_ranking.csv`
  - `q4_sensor_layout_results_overnight/*/*/paper/q4_snr_performance.csv`
  - `q4_sensor_layout_results_overnight/*/*/paper/*.png`
- Raw/trace:
  - `q4_sensor_layout_results_overnight/*/*/raw/q4_detection_trials.csv`
  - `q4_sensor_layout_results_overnight/*/*/raw/q4_false_alarm_trials.csv`
  - `q4_sensor_layout_results_overnight/*/*/raw/q4_runtime.txt`
  - `q4_sensor_layout_results_overnight/pc1_run_log.txt`
  - `q4_sensor_layout_results_overnight/pc2_run_log.txt`
- Logs:
  - `q4_sensor_layout/.log/change/q4_overnight_test_plan_20260619.md`
  - `q4_sensor_layout/.log/change/q4_universal_plan_review_20260620.md`
  - `q4_sensor_layout/.log/change/q4_v0_stage_closeout_20260620.md`

## Next Step

- Push or commit V0 as the finite-candidate robust layout baseline.
- Start V1 on a separate branch only after V0 is saved.
- V1 should be a new module, not an in-place rewrite of V0:
  - proposed name: `q4_adaptive_sensor_layout/`
  - proposed result directory: `q4_adaptive_sensor_layout_results/`
