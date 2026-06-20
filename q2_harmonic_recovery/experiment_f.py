"""Experiment F: Q2 residual diagnostics + GLRT re-scan on residuals.

Covers review issues:
  - #26: Q2 white-noise diagnostics (Ljung-Box, Jarque-Bera)
  - #48: GLRT re-scan on Q2 residuals after removing 2 Hz component

Run: python -m q2_harmonic_recovery.experiment_f
"""

from __future__ import annotations

import csv
import math
import time
from pathlib import Path

import numpy as np
from scipy import stats

from q1_model_compare import (
    Config,
    estimate_glrt_threshold,
    estimate_sinusoid,
    glrt_stat_from_fft,
    preprocess,
    load_single_source,
)

# ── helpers ──────────────────────────────────────────────────────────


def harmonic_fit(t: np.ndarray, x: np.ndarray, freq: float) -> dict:
    """Fit A*sin(2*pi*f*t+phi) + offset via least squares (Q2 convention)."""
    tc = t - float(np.mean(t))
    angle = 2.0 * np.pi * freq * tc
    design = np.column_stack([np.sin(angle), np.cos(angle), np.ones_like(tc)])
    beta = np.linalg.lstsq(design, x, rcond=None)[0]
    a, b, offset = map(float, beta)
    fit_signal = design @ beta
    residual = x - fit_signal
    amplitude = math.hypot(a, b)
    phase = float(np.angle(np.exp(1j * math.atan2(b, a) - 1j * 2.0 * np.pi * freq * float(np.mean(t)))))
    return {
        "frequency_hz": freq,
        "amplitude": amplitude,
        "phase_origin_rad": phase,
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "explained_variance": float(1.0 - np.var(residual) / np.var(x)),
        "fit": fit_signal,
        "residual": residual,
    }


def ljung_box(resid: np.ndarray, lags: int = 100) -> dict:
    """Ljung-Box portmanteau test using scipy-only implementation."""
    acf_n = len(resid)
    # compute autocorrelation up to `lags`
    acf = np.array([1.0] + [float(np.corrcoef(resid[:-k], resid[k:])[0, 1]) for k in range(1, lags + 1)])
    q_stat = float(acf_n * (acf_n + 2) * np.sum(acf[1:]**2 / (acf_n - np.arange(1, lags + 1))))
    p_val = float(1.0 - stats.chi2.cdf(q_stat, lags))
    return {"q_statistic": q_stat, "p_value": p_val, "lags": lags}


# ── main ─────────────────────────────────────────────────────────────


def main():
    t0 = time.perf_counter()
    workspace = Path(__file__).resolve().parents[1]
    candidates = [
        workspace / "data.xlsx",
        workspace.parent / "A题：机械设备故障检测" / "data.xlsx",
    ]
    data_path = None
    for path in candidates:
        if path.exists():
            data_path = path
            break
    if data_path is None:
        raise FileNotFoundError(f"Cannot find data.xlsx. Tried: {candidates}")

    print("Experiment F: Q2 residual diagnostics + GLRT re-scan")
    print(f"  data: {data_path}")

    # 1. Load data
    t, x, fs = load_single_source(data_path)
    print(f"  N={len(t)}, fs={fs} Hz, duration={t[-1]-t[0]:.1f} s")

    # 2. Fit the known 2 Hz component
    y = preprocess(x)
    fit = harmonic_fit(t, y, 2.0000016)
    residual = fit["residual"]
    print(f"  Fit: f={fit['frequency_hz']:.7f} Hz, A={fit['amplitude']:.6f}, "
          f"phi={fit['phase_origin_rad']:.6f} rad")
    print(f"  Residual std={float(np.std(residual)):.6f}, "
          f"explained var={fit['explained_variance']*100:.4f}%")

    # 3. Residual diagnostics
    skew = float(stats.skew(residual))
    kurt = float(stats.kurtosis(residual))  # excess kurtosis
    max_acf = float(
        max(abs(np.corrcoef(residual[:-k], residual[k:])[0, 1]) for k in range(1, 101))
    )
    jb_stat, jb_p = stats.jarque_bera(residual)
    lb_result = ljung_box(residual, lags=100)

    print(f"  Diagnostics:")
    print(f"    skewness={skew:.4f}")
    print(f"    excess_kurtosis={kurt:.4f}")
    print(f"    max|ACF|(1-100)={max_acf:.4f}")
    print(f"    Jarque-Bera: stat={jb_stat:.4f}, p={jb_p:.6f}")
    print(f"    Ljung-Box(100): Q={lb_result['q_statistic']:.4f}, p={lb_result['p_value']:.6f}")

    # 4. GLRT re-scan on residuals
    cfg = Config(
        data_path=data_path,
        output_dir=workspace / "q2_experiment_f_results",
        f_min=0.05,
        f_max=49.5,
        p_fa=0.05,
        glrt_mc=500,
        sim_mc=8,
        random_seed=20260619,
    )

    freqs, T_f = glrt_stat_from_fft(residual, fs, cfg)
    mask = (freqs >= cfg.f_min) & (freqs <= cfg.f_max)
    search_freqs = freqs[mask]
    search_stat = T_f[mask]
    max_idx = int(np.argmax(search_stat))
    max_f = float(search_freqs[max_idx])
    max_T = float(search_stat[max_idx])

    threshold = estimate_glrt_threshold(len(residual), fs, cfg)
    any_detected = max_T >= threshold
    print(f"  GLRT re-scan:")
    print(f"    max T(f) = {max_T:.4f} at f = {max_f:.5f} Hz")
    print(f"    threshold (P_FA=0.05) = {threshold:.4f}")
    print(f"    any frequency detected: {any_detected}")

    # 5. Write outputs
    out_dir = Path(workspace / "q2_experiment_f_results")
    out_dir.mkdir(parents=True, exist_ok=True)

    # -- residual diagnostics CSV
    diag_path = out_dir / "q2_residual_diagnostics.csv"
    with open(diag_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["sample_count", len(residual)])
        w.writerow(["residual_std", float(np.std(residual))])
        w.writerow(["skewness", skew])
        w.writerow(["excess_kurtosis", kurt])
        w.writerow(["max_abs_autocorr_lag_1_100", max_acf])
        w.writerow(["jarque_bera_statistic", jb_stat])
        w.writerow(["jarque_bera_p_value", jb_p])
        w.writerow(["ljung_box_statistic", lb_result["q_statistic"]])
        w.writerow(["ljung_box_p_value", lb_result["p_value"]])
        w.writerow(["ljung_box_lags", lb_result["lags"]])
    print(f"  Saved: {diag_path}")

    # -- GLRT scan CSV (just the peak + threshold info)
    scan_path = out_dir / "q2_residual_glrt_scan.csv"
    with open(scan_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["max_T", "frequency_hz", "threshold", "any_detected"])
        w.writerow([max_T, max_f, threshold, any_detected])
    print(f"  Saved: {scan_path}")

    elapsed = time.perf_counter() - t0
    print(f"  Done in {elapsed:.3f} s")


if __name__ == "__main__":
    main()
