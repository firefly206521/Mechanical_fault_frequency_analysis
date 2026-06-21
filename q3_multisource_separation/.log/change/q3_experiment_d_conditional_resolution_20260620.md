# Q3 实验 D：条件化近频辨识性能曲面

## Scope

- 关闭 `paper/review_issues.json` 中 issue #47。
- 将 Q3 “辨识极限”从单一数字改为条件化经验曲面：
  `P_success = g(T, SNR_weak, A_weak:A_strong, Delta f, Delta phi)`。
- 不修改 Q3 核心检测算法，只新增独立实验入口和结果目录。

## Code Changes

- 新增 `q3_multisource_separation/run_q3_experiment_d.py`。
- 输出目录：`q3_experiment_d_results/`。
- 输出结构：
  - `paper/q3_experiment_d_report.md`
  - `paper/q3_experiment_d_success_surface.csv`
  - `paper/q3_experiment_d_resolution_limits.csv`
  - `paper/q3_experiment_d_phase_effect.csv`
  - `paper/q3_experiment_d_success_surface.png`
  - `paper/q3_experiment_d_phase_effect.png`
  - `raw/q3_experiment_d_trials.csv`
  - `raw/q3_experiment_d_runtime.json`
- 运行中发现直接调用 `close_pair_resolver` 会在 `Delta f=0.015 Hz` 产生明显非单调伪影，因此废弃该结果，正式结果改用完整 `detect_multitone` 流程。

## Parameters

- `N=40001`
- `fs=100 Hz`
- `T=400 s`
- center frequency: `5 Hz`
- weak amplitude: `0.01`
- weak-component SNR: `-6, -12, -18 dB`
- amplitude ratios: `1:1, 1:3, 1:10`
- separations: `0.001, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.008, 0.010, 0.015, 0.020 Hz`
- random phase: uniform on `[0, 2pi)`
- Monte Carlo: `200` per grid cell
- detector: complete Q3 GLRT-SIC-joint-refinement-BIC flow
- GLRT threshold MC: `500`
- `max_components=4`
- `Delta BIC=10`
- seed: `20260620`

## Commands

```powershell
python -m compileall .\q3_multisource_separation
python -m q3_multisource_separation.run_q3_experiment_d --profile smoke --runs 1 --workers 4 --output-dir q3_experiment_d_results_smoke
python -m q3_multisource_separation.run_q3_experiment_d --profile official --workers 8 --output-dir q3_experiment_d_results
python C:\Users\Firefly\.codex\skills\paper-output-optimizer\scripts\check_result_tree.py .\q3_experiment_d_results
```

## Validation Evidence

- `compileall` passed.
- Result tree check passed with no issues.
- Raw trial rows: `18000`.
- Paper surface rows: `90`.
- Phase-effect rows: `90`.
- Empirical-limit rows: `9`.
- Runtime: `6243.25 s` with `8` workers.

## Key Results

| Weak SNR/dB | Amplitude ratio | 90% empirical limit/Hz |
|---:|---:|---:|
| -6 | 1:1 | 0.002 |
| -6 | 1:3 | 0.0025 |
| -6 | 1:10 | 0.003 |
| -12 | 1:1 | 0.002 |
| -12 | 1:3 | 0.0025 |
| -12 | 1:10 | 0.003 |
| -18 | 1:1 | 0.002 |
| -18 | 1:3 | 0.0025 |
| -18 | 1:10 | 0.003 |

The 90% limit is defined as the smallest tested separation whose success rate is at least 90% and remains at least 90% for all larger tested separations.

## Known Limits

- The result is empirical under the stated grid and random phase distribution.
- The phase diagnostic uses 8 bins over folded phase difference `[0, pi]`; the worst bin is an empirical diagnostic, not a strict theoretical lower bound.
- Because the complete Q3 detector is used, runtime is materially higher than the close-pair-only diagnostic.
- The fixed center frequency at `5 Hz` avoids boundary effects but does not prove frequency-independent behavior over the full band.

## Paper Wording

Use “under `T=400 s`, specified weak-component SNR, amplitude ratio, and random phase distribution, the 90% empirical resolution boundary is ...”. Do not write `0.0025 Hz` as a fixed theoretical or algorithmic limit.
