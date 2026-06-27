# Q3 Experiment D CuPy Application Foundation - 2026-06-26

## Scope

- Branch/worktree: `codex/q3-cupy-application-foundation` in `E:\AIworkspace\2026CSU-math\testA_cupy_worktree`.
- Purpose: build a GPU batch-computation foundation for future applications, no longer constrained by paper-result reproducibility.
- The existing CPU `complete` detector and `cpu_cached` path remain available as the trusted baseline.
- Main workspace `master` was dirty, so this work was isolated in a separate Git worktree.

## Environment

- GPU: NVIDIA GeForce RTX 5060 Laptop GPU.
- Driver: 573.24.
- GPU memory: about 8 GB.
- Python: 3.13.9, Anaconda.
- CuPy: 14.1.1.
- CUDA runtime reported by CuPy: 12090.
- Installed packages:
  - `cupy-cuda12x`
  - `nvidia-cufft-cu12`
  - `nvidia-cublas-cu12`
  - `cupy-cuda12x[ctk]` dependencies.

## Code Changes

- Added `q3_multisource_separation/cupy_batch.py`.
- Added `--compute-backend cpu|cpu_cached|cupy_batch` to `run_q3_experiment_d.py`.
- Added GPU batch controls:
  - `--cupy-batch-size`
  - `--cupy-center-span-hz`
  - `--cupy-center-step-hz`
  - `--cupy-separation-min-hz`
  - `--cupy-separation-max-hz`
  - `--cupy-separation-step-hz`
- GPU path uses one main process and does not initialize CuPy inside Python workers.
- GPU detector uses batched two-tone variable projection on a candidate pair grid.
- SSE kernel was optimized from batched small `solve` calls to the quadratic form `rhs^T G^{-1} rhs`.

## Validation Commands

```powershell
python -m compileall q3_multisource_separation

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --compute-backend cupy_batch --cupy-batch-size 4 --output-dir q3_experiment_results/d_cupy_smoke --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cupy_batch --cupy-batch-size 8 --output-dir q3_experiment_results/d_cupy_compare_8_inv --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cpu_cached --workers 1 --output-dir q3_experiment_results/d_cpu_cached_compare_8 --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cupy_batch --cupy-batch-size 64 --output-dir q3_experiment_results/d_cupy_benchmark_360 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cpu_cached --workers 8 --chunksize 1 --output-dir q3_experiment_results/d_cpu_cached_benchmark_360 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 40 --compute-backend cupy_batch --cupy-batch-size 128 --output-dir q3_experiment_results/d_cupy_benchmark_1800 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 400 --compute-backend cupy_batch --cupy-batch-size 256 --output-dir q3_experiment_results/d_cupy_benchmark_18000 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail
```

## Timing Results

| Run | Rows | Backend | Total runtime/s | GPU batch sum/s | Success rate |
|---|---:|---|---:|---:|---:|
| 8-row CPU baseline | 8 | `cpu_cached`, 1 worker | 10.609 | - | 100.0% |
| 8-row GPU | 8 | `cupy_batch` | 2.510 | 0.512 | 100.0% |
| 360-row CPU baseline | 360 | `cpu_cached`, 8 workers | 81.979 | - | 86.4% |
| 360-row GPU | 360 | `cupy_batch` | 3.582 | 1.182 | 99.2% |
| 1800-row GPU | 1800 | `cupy_batch` | 7.923 | 2.864 | 99.3% |
| 18000-row GPU | 18000 | `cupy_batch` | 39.331 | 16.505 | 99.5% |

The 18,000-row workload that previously took about two hours on the CPU path now completes in under one minute on the GPU batch path.

## Correctness and Interpretation

- The GPU path is not a drop-in acceleration of the old CPU `complete` detector.
- It is a new batched near-frequency detector that uses the experiment-D known center frequency and a pair-grid variable-projection search.
- On the 360-row comparison, `success` differed in 46 rows:
  - CPU `complete` success rate: about 86.4%.
  - GPU pair-grid success rate: about 99.2%.
- There were no `ill_conditioned` mismatches in the 360-row comparison.
- This is acceptable for an application-foundation branch, but it should not be described as reproducing the old detector.

## Known Limits

- The current GPU detector is optimized for the two-tone close-frequency experiment-D structure.
- It assumes the center frequency is supplied by the experiment/application layer.
- It estimates on a grid; frequency outputs can be exact grid points rather than continuous least-squares refinements.
- It currently generates deterministic signals/noise on CPU and transfers each batch to GPU; future work can move random generation to GPU when exact CPU comparability is no longer required.
- CuPy prints a CUDA path warning in this environment, but FFT and matrix operations work after installing the CUDA toolkit dependencies.

## Next Steps

- Add an optional CPU refinement pass for top GPU candidates if continuous frequency estimates are required.
- Add a larger center-span benchmark if future applications cannot supply a reliable center frequency.
- Consider a GPU random-generation mode for fully GPU-side simulation once seed-level CPU comparability is no longer needed.
- Keep `cpu_cached` as the oracle for regression tests, but treat `cupy_batch` as a separate detector family.

## Full-Auto GPU Spike - 2026-06-26

### Scope

- Added `--compute-backend cupy_full_auto`.
- This backend no longer uses the true experiment center frequency as a supplied detector center.
- It uses a two-stage GPU workflow:
  1. Batched FFT coarse search over `--cupy-auto-f-min-hz` to `--cupy-auto-f-max-hz`.
  2. Local GPU center/separation grid search around each observation's coarse FFT peak.
- The CPU `cpu_cached` baseline and the previous `cupy_batch` known-center backend remain unchanged.

### Added Controls

- `--cupy-auto-f-min-hz`
- `--cupy-auto-f-max-hz`
- `--cupy-auto-center-span-hz`
- `--cupy-auto-center-step-hz`
- `--cupy-auto-row-batch-size`
- `--cupy-auto-candidate-chunk-size`

### Validation Commands

```powershell
python -m compileall q3_multisource_separation

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --compute-backend cupy_full_auto --cupy-batch-size 2 --cupy-auto-row-batch-size 1 --cupy-auto-candidate-chunk-size 32 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_full_auto_smoke --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cupy_full_auto --cupy-batch-size 8 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_full_auto_compare_8 --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cupy_full_auto --cupy-batch-size 64 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_full_auto_benchmark_360 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 40 --compute-backend cupy_full_auto --cupy-batch-size 64 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_full_auto_benchmark_1800 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail
```

### Timing Results

| Run | Rows | Backend | Total runtime/s | Success rate | Notes |
|---|---:|---|---:|---:|---|
| 360-row CPU baseline | 360 | `cpu_cached`, 8 workers | 81.979 | 86.4% | Existing CPU reference run |
| 1800-row known-center GPU | 1800 | `cupy_batch` | 7.923 | 99.3% | Uses supplied center frequency |
| 360-row full-auto GPU | 360 | `cupy_full_auto` | 63.841 | 88.3% | FFT coarse center plus local grid |
| 1800-row full-auto GPU | 1800 | `cupy_full_auto` | 310.638 | 89.9% | No supplied center frequency |

The 1800-row `cupy_full_auto` run projects to about 3106 s, or 51.8 min, for 18,000 rows under the same grid and batch parameters.

### Timing Breakdown for 1800-Row Full-Auto Run

- Total runtime: 310.638 s.
- Sum of GPU coarse FFT time: 0.534 s.
- Sum of local pair-grid search time: 279.825 s.
- Sum of one-tone comparison time: 17.594 s.
- Mean absolute FFT coarse-center error against the simulated center: 0.00137 Hz.
- Maximum absolute FFT coarse-center error against the simulated center: 0.00262 Hz.

This shows that removing the supplied center frequency is not itself expensive; the cost comes from evaluating the extra local center grid around each observation.

### Negative Tuning Result

Increasing the local tensor block from `--cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128` to `8/256` made the 360-row run much slower:

| Run | Rows | Backend | Total runtime/s | Success rate |
|---|---:|---|---:|---:|
| 360-row full-auto default block | 360 | `cupy_full_auto` | 63.841 | 88.3% |
| 360-row full-auto larger block | 360 | `cupy_full_auto` | 552.811 | 88.3% |

The likely cause is memory pressure and oversized temporary trigonometric tensors. Larger GPU chunks are not automatically faster for this kernel.

### Current Interpretation

- `cupy_batch` is a very fast known-center near-frequency kernel.
- `cupy_full_auto` is the fairer no-known-center GPU prototype, but its current local grid search is much slower.
- The current 18,000-row full-auto estimate is around 52 minutes, not the sub-minute known-center result.
- The next optimization target is not FFT; it is reducing the local pair-grid SSE cost.

### Recommended Next Technical Step

- Keep `cupy_full_auto` as the correctness-oriented prototype.
- Add a two-pass local search:
  1. Coarse local grid with larger center/separation steps.
  2. Fine grid only around the top few candidates.
- This should reduce candidate-pair count without reintroducing true-center prior knowledge.

## Adaptive GPU Backend - 2026-06-26

### Scope

- Added `--compute-backend cupy_adaptive`.
- The backend implements a pilot-calibrated fast path:
  1. Run deterministic pilot replicates per experiment cell with `cupy_full_auto`.
  2. Learn a local center and center-span policy from pilot estimates.
  3. Run remaining rows through the fast learned-center `cupy_batch` kernel.
  4. Audit a deterministic subset with `cupy_full_auto`.
- The adaptive backend does not use the true experiment center as a detector input. Runtime metadata records `adaptive_uses_true_center=false`.

### Code Changes

- Added `q3_multisource_separation/adaptive_cupy.py`.
- Extended `run_q3_experiment_d.py` with:
  - `--compute-backend cupy_adaptive`
  - `--adaptive-pilot-runs-per-cell`
  - `--adaptive-audit-rate`
  - `--adaptive-min-center-span-hz`
  - `--adaptive-center-margin-hz`
  - `--adaptive-max-center-span-hz`
  - `--adaptive-audit-frequency-tolerance-hz`
- Added adaptive outputs:
  - `raw/q3_experiment_d_adaptive_policy.csv/json`
  - `raw/q3_experiment_d_adaptive_pilot_trials.csv`
  - `raw/q3_experiment_d_adaptive_audit_trials.csv`
  - `raw/q3_experiment_d_adaptive_audit_discrepancies.csv`
  - `raw/q3_experiment_d_adaptive_timing.csv`

### Validation Commands

```powershell
python -m compileall q3_multisource_separation

python -m q3_multisource_separation.run_q3_experiment_d --help

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 4 --compute-backend cupy_adaptive --cupy-batch-size 4 --adaptive-pilot-runs-per-cell 2 --adaptive-audit-rate 0.5 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_smoke2 --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 8 --compute-backend cupy_adaptive --cupy-batch-size 64 --adaptive-pilot-runs-per-cell 3 --adaptive-audit-rate 0.05 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_benchmark_360 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 40 --compute-backend cupy_adaptive --cupy-batch-size 64 --adaptive-pilot-runs-per-cell 3 --adaptive-audit-rate 0.05 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_benchmark_1800 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail
```

### Timing Results

| Run | Rows | Backend | Total runtime/s | Success rate | Audit mismatch |
|---|---:|---|---:|---:|---:|
| 360-row full-auto GPU | 360 | `cupy_full_auto` | 63.841 | 88.3% | - |
| 360-row adaptive GPU | 360 | `cupy_adaptive` | 61.503 | 88.1% | 0/45 |
| 1800-row full-auto GPU | 1800 | `cupy_full_auto` | 310.638 | 89.9% | - |
| 1800-row adaptive GPU | 1800 | `cupy_adaptive` | 71.194 | 89.6% | 0/90 |
| 1800-row known-center GPU | 1800 | `cupy_batch` | 7.923 | 99.3% | - |

The 1800-row adaptive run projects to about 712 s, or 11.9 min, for 18,000 rows under the same settings.

### 1800-Row Adaptive Breakdown

- Pilot rows: 135.
- Fast rows: 1665.
- Audit rows: 90.
- Pilot time: 23.277 s.
- Fast time: 30.933 s.
- Audit time: 15.317 s.
- Audit mismatches: 0.

### Interpretation

- `cupy_adaptive` is much closer to a fair no-true-center workflow than `cupy_batch`, because learned centers come from pilot rows.
- At 360 rows, pilot overhead dominates and adaptive is only slightly faster than full-auto.
- At 1800 rows, the same pilot cost is amortized and adaptive is about 4.36x faster than `cupy_full_auto`.
- It is still slower than known-center `cupy_batch`, which is expected because adaptive pays pilot and audit costs and does not receive the true center.

### Next Optimization Target

- Add an optional expansion round only for audited cells with mismatches.
- Add a policy reuse mode so a learned adaptive policy can be loaded for repeated same-distribution jobs.
- Consider learning a two-stage center span: narrow span for confident cells and full-auto fallback for low-confidence cells.

## Adaptive Fallback and 18,000-Row Validation - 2026-06-26

### Scope

- Added a fast-path fallback mechanism for suspected adaptive errors.
- Fallback triggers:
  - fast path estimates `estimated_k != 2`;
  - fast path is marked ill-conditioned;
  - estimated center lies near the learned center-span boundary.
- Triggered rows are recomputed with `cupy_full_auto` and replace the main trial result.
- Added `raw/q3_experiment_d_adaptive_fallback_events.csv`.
- Increased the success-check numerical epsilon from `1e-8 Hz` to `1e-7 Hz` to avoid classifying grid-roundoff cases just outside `Delta f / 4` as failures. This is much smaller than the minimum tested tolerance, `0.00025 Hz`.

### Validation Commands

```powershell
python -m compileall q3_multisource_separation

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 40 --compute-backend cupy_adaptive --cupy-batch-size 64 --adaptive-pilot-runs-per-cell 3 --adaptive-audit-rate 0.05 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_fallback_benchmark_1800 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 400 --compute-backend cupy_adaptive --cupy-batch-size 64 --adaptive-pilot-runs-per-cell 3 --adaptive-audit-rate 0.05 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_fallback_eps1e7_benchmark_18000 --snr-levels=-6,-12,-18 --amplitude-ratios=1,3,10 --separations=0.001,0.002,0.0025,0.003,0.004 --timing-detail
```

### Final 18,000-Row Result

| Metric | Value |
|---|---:|
| Rows | 18,000 |
| Runtime | 278.826 s |
| Successes | 17,288 |
| Success rate | 96.04% |
| Pilot rows | 135 |
| Fast rows | 17,865 |
| Fallback rows | 137 |
| Fallback fixed successes | 35 |
| Audit rows | 900 |
| Audit mismatches | 0 |
| Mean learned-center absolute error | 0.000125 Hz |
| Max learned-center absolute error | 0.000125 Hz |
| Learned center span | 0.001 Hz for all cells |
| Policies outside learned span | 0 |

### Timing Breakdown

| Stage | Time/s |
|---|---:|
| Pilot full-auto | 22.115 |
| Fast learned-center batch | 83.530 |
| Fallback full-auto | 21.958 |
| Audit full-auto | 148.827 |
| Total adaptive orchestration | 277.036 |

The audit stage dominates the final run because it verifies 900 rows with `cupy_full_auto`.

### Center Misjudgment Findings

- No learned center policy exceeded its learned span when compared to the known simulation center for diagnostic purposes.
- No fallback was triggered by center-boundary risk in the 18,000-row run.
- All 137 fallback events were triggered by fast-path single-frequency collapse (`estimated_k`).
- Fallback changed 60 rows and fixed 35 unsuccessful rows.
- The final audit found 0 mismatches out of 900 audited rows.

This supports the current interpretation: under this experiment grid, the main adaptive failure mode is not center-frequency policy misjudgment, but close-frequency collapse into a one-tone decision at the hardest `Delta f=0.001 Hz` cases.

### Worst Cells

The lowest success rates remain at `Delta f=0.001 Hz`, which is the hardest tested separation:

| SNR/dB | Ratio | Separation/Hz | Success rate |
|---:|---:|---:|---:|
| -18 | 1:1 | 0.001 | 53.5% |
| -12 | 1:3 | 0.001 | 71.0% |
| -6 | 1:3 | 0.001 | 71.0% |
| -18 | 1:3 | 0.001 | 72.0% |
| -12 | 1:1 | 0.001 | 84.0% |

### Interpretation

- The adaptive backend now has a concrete misjudgment handling path: suspicious fast rows are recomputed by `cupy_full_auto` before writing the main trial output.
- The 96.04% final success rate is not solely from fallback. It combines:
  - numerical-boundary correction via `SUCCESS_EPS_HZ=1e-7`;
  - full-auto fallback on fast single-frequency collapse;
  - the original learned-center fast path.
- The result should be described as an adaptive application backend, not a drop-in equivalent of the original CPU `complete` detector.

### Recommended Next Step

- Add policy reuse/load support for repeated same-distribution jobs.
- Add a cell-level expansion mode only if future audit mismatches appear.
- Keep `cupy_full_auto` available as the verifier and fallback oracle.

## Forced Center-Misjudgment Stress Test - 2026-06-27

### Purpose

The earlier 18,000-row run did not naturally produce learned-center policy failures. To test whether `cupy_adaptive` can recover after a wrong policy, a controlled stress knob was added:

- `--adaptive-policy-center-offset-hz`
- Default is `0.0`, so existing non-stress runs are unchanged.
- In stress mode, the policy learned by pilot full-auto is shifted after learning and before fast-path execution.
- The runtime metadata records `adaptive_policy_center_offset_hz`, and policy rows preserve both the shifted center and `adaptive_policy_center_hz_unshifted`.

This is an injected failure mode, not a normal scientific result.

### Stress Setup

```powershell
python -m compileall q3_multisource_separation

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 20 --compute-backend cupy_adaptive --cupy-batch-size 32 --adaptive-pilot-runs-per-cell 3 --adaptive-audit-rate 0.2 --adaptive-disable-fallback --adaptive-policy-center-offset-hz 0.003 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_stress_offset_no_fallback --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail

python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 20 --compute-backend cupy_adaptive --cupy-batch-size 32 --adaptive-pilot-runs-per-cell 3 --adaptive-audit-rate 0.2 --adaptive-policy-center-offset-hz 0.003 --cupy-auto-row-batch-size 4 --cupy-auto-candidate-chunk-size 128 --cupy-auto-center-span-hz 0.003 --cupy-auto-center-step-hz 0.00025 --cupy-separation-min-hz 0.0005 --cupy-separation-max-hz 0.004 --cupy-separation-step-hz 0.00025 --output-dir q3_experiment_results/d_cupy_adaptive_stress_offset_with_fallback_v2 --snr-levels=-6 --amplitude-ratios=1 --separations=0.002 --timing-detail
```

### Observed Failure Without Fallback

| Metric | Value |
|---|---:|
| Rows | 20 |
| Pilot rows | 3 |
| Fast rows | 17 |
| Successes | 3 |
| Fast successes | 0 |
| Audit rows | 4 |
| Audit mismatches | 4 |

The policy learned center was about `5.000125 Hz`; the injected policy center was about `5.003125 Hz` with span `0.001 Hz`. The fast estimates were pulled to the wrong local window or to separation-grid boundaries, while full-auto audit returned frequencies near the true `5 Hz` center.

### Fallback Improvement

The first fallback rule only checked estimated component count, ill-conditioning, and center-window boundary. It recovered part of the stress case but missed rows whose estimated separation stuck to the search-grid minimum or maximum. The fallback risk check was extended with:

- `separation_min_boundary`
- `separation_max_boundary`

This means a fast result that lands on the edge of the local separation grid is treated as suspicious and recomputed with `cupy_full_auto`.

### Recovery Result

| Metric | Value |
|---|---:|
| Rows | 20 |
| Pilot rows | 3 |
| Fast rows before fallback | 17 |
| Fallback rows | 17 |
| Fallback successes | 17 |
| Final successes | 20 |
| Changed fallback results | 17 |
| Audit rows | 4 |
| Audit mismatches | 0 |
| Adaptive total time | 6.51 s |

Fallback reasons in the recovered run:

| Reason | Count |
|---|---:|
| `center_boundary;separation_max_boundary` | 9 |
| `separation_min_boundary` | 4 |
| `center_boundary;separation_min_boundary` | 3 |
| `separation_max_boundary` | 1 |

### Conclusion

The injected `+0.003 Hz` policy-center error successfully induced adaptive fast-path misjudgment. With fallback disabled, the fast path failed all non-pilot rows and audit caught the error. With fallback enabled and separation-boundary risk checks added, all suspicious fast rows restarted through `cupy_full_auto`, the final main rows recovered to `20/20` success, and audit found no mismatches.

This supports the current recovery design:

- fast learned-center path is allowed to be aggressive;
- boundary or collapse symptoms trigger a local restart through the trusted full-auto GPU path;
- audit remains an independent check and does not rewrite rows by default.
