# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Before starting any task, scan for available skills with `Skill` — project-level `.claude/skills/` and user-level `~/.claude/skills/`. Invoke matching skills before writing code or running experiments.

## Project overview

Mathematical modeling competition (2026 CSU A题): detect weak sinusoidal fault frequencies in strong noise, recover waveforms, separate multiple sources, and optimize sensor layout. Four questions, each implemented as an independent Python package.

**Signal model:** $x(t)=A\sin(2\pi ft+\phi)+n(t)$, fs=100 Hz, N≈40001 (400 s duration).

## Authoritative result directories (one per question)

| Question | Directory |
|----------|-----------|
| Q1 GLRT | `q1_glrt_results_n40001/` |
| Q1 model compare | `q1_results_n40001/` |
| Q2 | `q2_harmonic_recovery_results/` |
| Q3 | `q3_multisource_separation_results_optimized/` |
| Q4 V1 | `q4_sensor_layout_v1_results_robustness_v2_medium/` |

All superseded results: `_archived/`. Cleanup log: `.log/change/project_cleanup_archive_20260620.md`.

## Package architecture (consistent across Q2–Q4)

Each question package follows the same pattern:

```
q{n}_*/__init__.py
q{n}_*/core.py          # Numerical logic, signal processing, fitting
q{n}_*/outputs.py       # CSV, Markdown report, figure generation
q{n}_*/cli.py or run_*.py  # CLI argument parsing + orchestration
q{n}_*/experiments.py   # Monte Carlo simulations (Q3, Q4 only)
```

**Q1** is the exception: it has both a top-level `q1_model_compare.py` (multi-model benchmark) and a `q1_glrt/` package (selected GLRT model), with `q1_glrt_model.py` as the compatibility entry point.

## Running each question

```powershell
# Q1 — GLRT detection + FFT comparison
python q1_glrt_model.py --data data.xlsx --output-dir q1_glrt_results_n40001 --sim-mc 200 --glrt-mc 500
python q1_model_compare.py --data data.xlsx --output-dir q1_results_n40001 --sim-mc 80

# Q2 — Harmonic waveform recovery (needs Q1 result as initial frequency)
python q2_harmonic_recovery/run_q2.py --bootstrap-runs 10000 --simulation-runs 200

# Q3 — Multi-source separation (SIC + BIC)
python -m q3_multisource_separation.run_q3 --simulation-runs 200 --resolution-runs 200 --null-runs 500 --extreme-runs 100 --workers 8 --output-dir q3_multisource_separation_results_optimized

# Q4 V1 — Adaptive sensor layout
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile smoke
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium --response-gain-jitter 0.15 --response-phase-jitter 0.20 --noise-correlation 0.30
```

## Running tests

Only Q4 V1 has unit tests:
```powershell
python -m pytest q4_adaptive_sensor_layout/tests -q
```

Syntax check for any package:
```powershell
python -m py_compile q{n}_*/core.py q{n}_*/outputs.py q{n}_*/cli.py
```

## Key shared parameters

- `fs` = 100 Hz, `N` = 40001 (must match across Q1/Q2/Q3 synthetic experiments)
- `P_FA` = 0.05 (target false-alarm rate for GLRT)
- `random_seed` = 20260619 (deterministic reproducibility)
- GLRT statistic: normalized periodogram $T(f)=2|\text{FFT}(f)|^2/(N\sigma^2)$
- GLRT threshold: pure-noise Monte Carlo, 95th percentile of $\max_f T(f)$
- Frequency refinement: bounded 1D least-squares (`scipy.optimize.minimize_scalar`) around coarse FFT-bin peak

## Critical design decisions and known issues

**FFT vs GLRT equivalence (Q1):** The GLRT statistic is a positive linear transform of the periodogram. On the same FFT grid with the same MC threshold, both methods produce identical detection results and frequency errors. This is mathematically expected (Kay 1998 §7.6, Scharf 1991 §6.4), not a bug. The paper should not claim different detection mechanisms. GLRT's value is the statistical framework's extensibility to Q2 (uncertainty quantification) and Q3 (BIC model selection). See `q1_glrt/.log/change/q1_stage_fix_review_issues.md`.

**Q1 FFT baseline:** `fft_peak_detect_signal()` in `q1_glrt/core.py` now uses the identical GLRT statistic + threshold computation path as `glrt_detect_signal()`. They are explicitly equivalent by design — do not "fix" by making them diverge.

**Q3 model:** SIC (successive interference cancellation) peels strongest components first, then joint harmonic regression + BIC for model order selection. BIC Δ≥10 for new component admission. SIC error propagation is a known limitation (documented in `需要重跑的实验.md` 实验组 I).

**Synthetic experiment N:** Q1 originally capped at N=12000 for runtime; this was fixed to N=40001. All new synthetic experiments must use N=40001 to match Q2 and the real data. See `q1_glrt/core.py:222` and `q1_model_compare.py:410`.

**Data source:** `data.xlsx`, sheets `单源故障` (Q1/Q2) and `多源故障` (Q3). Q4 uses Q3 detected frequencies as source parameters.

## Paper

`paper/paper.tex` — uses `cumcmthesis` document class, compiled with XeLaTeX. References in `paper/refer.bib`. `paper/review_issues.json` tracks 50 review items (P0–P3). `paper/需要重跑的实验.md` lists experiments that need code changes + rerun, organized into groups A–I.

## Dependencies

Python ≥3.10, numpy, scipy, pandas, matplotlib, scikit-learn (Q1 model compare only).
