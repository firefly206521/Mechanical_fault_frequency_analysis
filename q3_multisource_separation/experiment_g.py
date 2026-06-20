"""Experiment G: Sensitivity analysis for key algorithmic parameters.

Covers review issue #50:
  Layer 1 — Real data sensitivity sweep: total α, ΔBIC, refinement half_width
  Layer 2 — GLRT threshold MC stability: MC repetitions vs threshold convergence

Run: python -m q3_multisource_separation.experiment_g
"""

from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from q2_harmonic_recovery.core import linear_detrend
from q3_multisource_separation.core import (
    GLRTConfig,
    SEED,
    component_table,
    detect_multitone,
    load_multi_source,
    q1_compatible_glrt_threshold,
    refine_joint_frequencies,
)


def locate_data(workspace: Path) -> Path:
    candidates = [
        workspace / "data.xlsx",
        workspace.parent / "A题：机械设备故障检测" / "data.xlsx",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Cannot find data.xlsx. Tried: {candidates}")


# ── Layer 1: Real data sensitivity sweep ──────────────────────────────


def _run_detection(t, y, fs, total_alpha, bic_delta, glrt_mc, max_components):
    """Run detect_multitone with given parameters, return key metrics."""
    cfg = GLRTConfig(
        f_min=0.05,
        f_max=49.5,
        p_fa=total_alpha / max_components,
        glrt_mc=glrt_mc,
        random_seed=SEED,
    )
    cfg = replace(cfg, threshold=q1_compatible_glrt_threshold(len(y), fs, cfg))

    # conditional threshold for close-pair resolver
    baseband_factor = max(1, int(round(fs / 1.0)))
    baseband_n = len(t[::baseband_factor])
    baseband_fs = fs / baseband_factor
    from q3_multisource_separation.core import conditional_glrt_threshold
    cfg = replace(
        cfg,
        conditional_threshold=conditional_glrt_threshold(
            baseband_n, baseband_fs, 0.000025, monte_carlo_runs=max(glrt_mc, 100),
        ),
    )

    t0 = time.perf_counter()
    fit, history = detect_multitone(t, y, fs, cfg, max_components=max_components, bic_delta=bic_delta)
    elapsed = time.perf_counter() - t0

    components = component_table(fit)
    return {
        "total_alpha": total_alpha,
        "per_step_p_fa": cfg.p_fa,
        "bic_delta": bic_delta,
        "glrt_mc": glrt_mc,
        "detected_k": len(components),
        "frequencies_hz": ";".join(f"{c['frequency_hz']:.12g}" for c in components),
        "amplitudes": ";".join(f"{c['amplitude']:.6g}" for c in components),
        "bic_final": fit["bic"],
        "explained_variance": fit["explained_variance"],
        "condition_design": fit["condition_design"],
        "iterations": len(history),
        "stop_reason": history[-1]["stop_reason"] if history else "no_history",
        "runtime_s": elapsed,
    }


def layer1_real_data_sweep(t, y, fs, output_dir: Path) -> list[dict]:
    """One-parameter-at-a-time sweep on real multi-source data."""
    print("=" * 60)
    print("Layer 1: Real data sensitivity sweep")
    max_components = 20
    baseline = {
        "total_alpha": 0.05,
        "bic_delta": 10.0,
        "glrt_mc": 500,
    }
    sweeps = [
        ("total_alpha", [0.01, 0.05, 0.10]),
        ("bic_delta", [6.0, 10.0, 20.0]),
        ("glrt_mc", [200, 500, 1000]),
    ]

    results = []
    # Baseline
    print(f"  baseline: α={baseline['total_alpha']}, ΔBIC={baseline['bic_delta']}, MC={baseline['glrt_mc']}")
    row = _run_detection(t, y, fs, **baseline, max_components=max_components)
    row["variant"] = "baseline"
    results.append(row)
    print(f"    K={row['detected_k']}, BIC={row['bic_final']:.1f}, "
          f"freqs={row['frequencies_hz']}, time={row['runtime_s']:.1f}s")

    for param_name, values in sweeps:
        for value in values:
            params = baseline.copy()
            params[param_name] = value

            label = f"{param_name}={value}"
            print(f"  {label}")
            row = _run_detection(t, y, fs, **params, max_components=max_components)
            row["variant"] = label
            results.append(row)
            print(f"    K={row['detected_k']}, BIC={row['bic_final']:.1f}, "
                  f"freqs={row['frequencies_hz']}, time={row['runtime_s']:.1f}s")

    # Save
    csv_path = output_dir / "q3_sensitivity_real_data.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)
    print(f"  Saved: {csv_path}")
    return results


# ── Layer 2: GLRT threshold MC stability ──────────────────────────────


def layer2_glrt_mc_stability(output_dir: Path) -> list[dict]:
    """Check how GLRT threshold varies with MC repetitions and seeds."""
    print("=" * 60)
    print("Layer 2: GLRT threshold MC stability")

    n = 40001
    fs = 100.0
    mc_values = [100, 200, 500, 1000, 2000, 5000]
    seeds = [SEED, SEED + 100, SEED + 200]
    p_fa_values = [0.01, 0.05, 0.10]

    results = []
    for p_fa in p_fa_values:
        for mc in mc_values:
            thresholds = []
            for seed in seeds:
                cfg = GLRTConfig(
                    f_min=0.05, f_max=49.5, p_fa=p_fa, glrt_mc=mc, random_seed=seed,
                )
                thresh = q1_compatible_glrt_threshold(n, fs, cfg)
                thresholds.append(thresh)

            mean_t = float(np.mean(thresholds))
            std_t = float(np.std(thresholds, ddof=1))
            cv_pct = float(std_t / mean_t * 100.0) if mean_t > 0 else float("nan")
            results.append({
                "p_fa": p_fa,
                "mc_runs": mc,
                "threshold_mean": mean_t,
                "threshold_std": std_t,
                "threshold_cv_pct": cv_pct,
                "threshold_min": float(np.min(thresholds)),
                "threshold_max": float(np.max(thresholds)),
                "threshold_range_pct": float((np.max(thresholds) - np.min(thresholds)) / mean_t * 100.0),
                "n_seeds": len(seeds),
            })
            print(f"  α={p_fa}, MC={mc:4d}: threshold={mean_t:.4f} ± {std_t:.4f} (CV={cv_pct:.2f}%)")

    csv_path = output_dir / "q3_sensitivity_glrt_mc_stability.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)
    print(f"  Saved: {csv_path}")
    return results


# ── Layer 3: Refinement half_width sensitivity ────────────────────────


def layer3_refinement_sensitivity(t, y, fs, output_dir: Path) -> list[dict]:
    """Test whether refinement half_width affects final frequency estimates."""
    print("=" * 60)
    print("Layer 3: Refinement half_width sensitivity")

    # Known Q3 frequencies from optimized_complete
    known_freqs = [3.999998173832588, 7.999928571466699, 13.00008888535092, 14.000023485389157]
    half_widths = [0.001, 0.003, 0.006, 0.012, 0.025]
    results = []
    for hw in half_widths:
        fit = refine_joint_frequencies(t, y, known_freqs, half_width=hw, maxiter=45)
        freqs_str = ";".join(f"{f:.12g}" for f in fit["frequencies_hz"])
        # max deviation from seeds
        deviations = [abs(f - s) for f, s in zip(fit["frequencies_hz"], known_freqs)]
        max_dev = float(np.max(deviations))
        results.append({
            "half_width_hz": hw,
            "frequencies_hz": freqs_str,
            "bic": fit["bic"],
            "condition_design": fit["condition_design"],
            "max_deviation_from_seed_hz": max_dev,
            "optimizer_message": fit.get("optimizer_message", ""),
        })
        print(f"  half_width={hw:.3f}: freqs={freqs_str}, max_dev={max_dev:.2e}, BIC={fit['bic']:.1f}")

    csv_path = output_dir / "q3_sensitivity_refinement.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)
    print(f"  Saved: {csv_path}")
    return results


# ── Synthesis ─────────────────────────────────────────────────────────


def _synthesise(all_results: dict, output_dir: Path) -> None:
    """Write a Markdown summary and JSON metadata."""
    l1 = all_results.get("layer1", [])
    l2 = all_results.get("layer2", [])
    l3 = all_results.get("layer3", [])

    # Determine stability: does K change?
    baseline_k = None
    k_stable = True
    k_values = set()
    for row in l1:
        k_values.add(row["detected_k"])
        if row.get("variant") == "baseline":
            baseline_k = row["detected_k"]
    if baseline_k is not None:
        k_stable = all(k == baseline_k for k in k_values)

    # Threshold CV for MC=500, α=0.05
    threshold_cv = None
    for row in l2:
        if row["p_fa"] == 0.05 and row["mc_runs"] == 500:
            threshold_cv = row["threshold_cv_pct"]

    # Refinement max deviation
    max_ref_dev = max(row["max_deviation_from_seed_hz"] for row in l3) if l3 else None

    lines = [
        "# Q3 实验组 G：敏感性分析",
        "",
        "## 第一层：真实数据参数扫描",
        f"- 基线参数：α=0.05, ΔBIC=10, MC=500",
        f"- 检测分量数 K 稳定：{'是' if k_stable else '否'}（观察值: {sorted(k_values)}）",
    ]
    for row in l1:
        lines.append(f"  - {row['variant']}: K={row['detected_k']}, BIC={row['bic_final']:.1f}, "
                     f"stop={row['stop_reason']}")

    lines += [
        "",
        "## 第二层：GLRT 门限 MC 稳定性",
        f"- α=0.05, MC=500 时门限 CV = {threshold_cv:.2f}%（3 种子）",
    ]
    for row in l2:
        lines.append(f"  - α={row['p_fa']}, MC={row['mc_runs']:4d}: "
                     f"threshold={row['threshold_mean']:.4f} ± {row['threshold_std']:.4f} "
                     f"(CV={row['threshold_cv_pct']:.2f}%, range={row['threshold_range_pct']:.2f}%)")

    lines += [
        "",
        "## 第三层：精修搜索半径",
        f"- 最大频率偏移 = {max_ref_dev:.2e} Hz",
    ]
    for row in l3:
        lines.append(f"  - half_width={row['half_width_hz']:.3f}: max_dev={row['max_deviation_from_seed_hz']:.2e}, "
                     f"BIC={row['bic']:.1f}")

    lines += [
        "",
        "## 结论",
        f"- 检测分量数 K 对参数选择{'不敏感' if k_stable else '敏感'}",
        f"- GLRT 门限在 MC=500 时变异系数约 {threshold_cv:.1f}%",
        f"- 精修半径对最终频率影响 < {max_ref_dev:.2e} Hz（{'可忽略' if max_ref_dev and max_ref_dev < 0.001 else '需关注'}）",
    ]

    report = "\n".join(lines)
    (output_dir / "q3_sensitivity_report.md").write_text(report, encoding="utf-8")
    print(f"  Report: {output_dir / 'q3_sensitivity_report.md'}")

    metadata = {
        "experiment": "Q3 Experiment Group G sensitivity analysis (#50)",
        "parameters_swept": {
            "total_alpha": [0.01, 0.05, 0.10],
            "bic_delta": [6.0, 10.0, 20.0],
            "glrt_mc": [200, 500, 1000],
            "mc_stability_mc_values": [100, 200, 500, 1000, 2000, 5000],
            "mc_stability_seeds": 3,
            "refinement_half_widths": [0.001, 0.003, 0.006, 0.012, 0.025],
        },
        "key_findings": {
            "k_stable": k_stable,
            "baseline_k": baseline_k,
            "observed_k_values": sorted(k_values),
            "threshold_cv_at_mc500_pct": threshold_cv,
            "max_refinement_deviation_hz": max_ref_dev,
        },
    }
    (output_dir / "q3_sensitivity_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )


# ── main ──────────────────────────────────────────────────────────────


def main():
    t0 = time.perf_counter()
    workspace = Path(__file__).resolve().parents[1]
    data_path = locate_data(workspace)
    out_dir = workspace / "q3_experiment_results" / "g"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Experiment G: Sensitivity analysis")
    print(f"  data: {data_path}")
    print(f"  output: {out_dir}")

    # Load real multi-source data
    t, raw, fs = load_multi_source(data_path)
    y, trend = linear_detrend(t, raw)
    print(f"  N={len(t)}, fs={fs} Hz, duration={t[-1]-t[0]:.1f} s")

    all_results = {}

    # Layer 1
    l1 = layer1_real_data_sweep(t, y, fs, out_dir)
    all_results["layer1"] = l1

    # Layer 2
    l2 = layer2_glrt_mc_stability(out_dir)
    all_results["layer2"] = l2

    # Layer 3
    l3 = layer3_refinement_sensitivity(t, y, fs, out_dir)
    all_results["layer3"] = l3

    # Synthesis
    _synthesise(all_results, out_dir)

    elapsed = time.perf_counter() - t0
    print(f"\n  Total: {elapsed:.1f} s")


if __name__ == "__main__":
    main()
