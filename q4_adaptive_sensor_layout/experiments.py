"""Experiment orchestration for Q4 V1 adaptive sensor layout."""

from __future__ import annotations

import time
import math
from collections import defaultdict

import numpy as np

from .core import (
    DEFAULT_AMPLITUDES,
    DEFAULT_FREQUENCIES,
    FAULT_LABELS,
    Q4V1Config,
    baseline_layouts,
    basis_matrices,
    calibrated_threshold,
    default_time_axis,
    evaluate_layout,
    exhaustive_layouts,
    fused_statistics,
    generate_candidate_points,
    greedy_layout,
    layout_name,
    layout_regions,
    noise_stds_for_snr,
    one_swap_search,
    prescreen_points,
    projection_statistics,
    synthesize_layout_samples,
    trial_rng,
)


PROFILE_DEFAULTS = {
    "smoke": {"grid_size": 36, "top_layouts": 5, "runs": 5, "false_alarm_runs": 10, "threshold_mc": 40, "duration_s": 12.0},
    "medium": {"grid_size": 96, "top_layouts": 8, "runs": 60, "false_alarm_runs": 120, "threshold_mc": 120, "duration_s": 30.0},
    "official": {"grid_size": 144, "top_layouts": 10, "runs": 200, "false_alarm_runs": 500, "threshold_mc": 300, "duration_s": 40.0},
}
SNR_LEVELS = (-25.0, -20.0, -15.0, -12.0, -10.0, -5.0)


def _mean_bool(rows: list[dict], key: str) -> float:
    if not rows:
        return float("nan")
    return float(np.mean([bool(row[key]) for row in rows]))


def _fault_rates(rows: list[dict]) -> list[float]:
    return [_mean_bool(rows, f"fault_{index + 1}_detected") for index in range(len(FAULT_LABELS))]


def _layout_rows(points, evaluations, benchmark_map: dict[str, str]) -> list[dict]:
    rows = []
    for rank, evaluation in enumerate(evaluations, 1):
        name = layout_name(points, evaluation.layout)
        rows.append({
            "rank": rank,
            "layout": name,
            "regions": layout_regions(points, evaluation.layout),
            "benchmark": benchmark_map.get(name, "v1_adaptive_candidate"),
            "objective": evaluation.objective,
            "robust_min_lambda": evaluation.robust_min_lambda,
            "mean_lambda": evaluation.mean_lambda,
            "detection_min_lambda": evaluation.detection_min_lambda,
            "detection_mean_lambda": evaluation.detection_mean_lambda,
            "trace_info": evaluation.trace_info,
            "logdet_info": evaluation.logdet_info,
            "min_eigen_info": evaluation.min_eigen_info,
            "redundancy": evaluation.redundancy,
        })
    return rows


def _candidate_rows(points) -> list[dict]:
    rows = []
    for index, point in enumerate(points):
        row = {
            "point_index": index,
            "point_id": point.point_id,
            "region": point.region,
            "x": point.x,
            "y": point.y,
            "z": point.z,
            "nx": point.nx,
            "ny": point.ny,
            "nz": point.nz,
            "noise_std": point.noise_std,
            "installable": point.installable,
        }
        for fault_index, label in enumerate(FAULT_LABELS):
            response = point.response[fault_index]
            row[f"response_abs_{label}"] = float(abs(response))
            row[f"response_phase_{label}"] = float(np.angle(response))
        rows.append(row)
    return rows


def _run_detection_trials(points, layout, layout_label: str, snr_levels: tuple[float, ...], runs: int, false_alarm_runs: int, cfg: Q4V1Config) -> list[dict]:
    rows: list[dict] = []
    t = default_time_axis(cfg)
    sin_basis, cos_basis = basis_matrices(t)
    for snr_db in snr_levels:
        noise_all = noise_stds_for_snr(points, snr_db)
        noise_stds = noise_all[list(layout)]
        threshold = calibrated_threshold(tuple(layout), tuple(np.round(noise_stds, 12)), cfg)
        for replicate in range(runs):
            rng = trial_rng(3000 + int(round(10 * snr_db)) + sum(layout), replicate, cfg.random_seed)
            samples, trial_noise = synthesize_layout_samples(points, tuple(layout), t, snr_db, rng)
            stats = projection_statistics(samples, sin_basis, cos_basis, trial_noise)
            fused = fused_statistics(stats, trial_noise)
            detected = fused >= threshold
            rows.append({
                "layout": layout_name(points, layout),
                "regions": layout_regions(points, layout),
                "benchmark": layout_label,
                "snr_db": snr_db,
                "replicate": replicate,
                "trial_type": "signal",
                "threshold": threshold,
                "detected_any": bool(np.any(detected)),
                "detected_all": bool(np.all(detected)),
                "source_detection_rate": float(np.mean(detected)),
                "false_alarm": False,
                **{f"fault_{index + 1}_detected": bool(value) for index, value in enumerate(detected)},
                **{f"fault_{index + 1}_statistic": float(value) for index, value in enumerate(fused)},
            })
        for replicate in range(false_alarm_runs):
            rng = trial_rng(8100 + int(round(10 * snr_db)) + sum(layout), replicate, cfg.random_seed)
            noise = rng.normal(0.0, noise_stds[:, None], (len(layout), len(t)))
            stats = projection_statistics(noise, sin_basis, cos_basis, noise_stds)
            fused = fused_statistics(stats, noise_stds)
            rows.append({
                "layout": layout_name(points, layout),
                "regions": layout_regions(points, layout),
                "benchmark": layout_label,
                "snr_db": snr_db,
                "replicate": replicate,
                "trial_type": "noise",
                "threshold": threshold,
                "detected_any": False,
                "detected_all": False,
                "source_detection_rate": 0.0,
                "false_alarm": bool(np.max(fused) >= threshold),
                **{f"fault_{index + 1}_detected": False for index in range(len(FAULT_LABELS))},
                **{f"fault_{index + 1}_statistic": float(value) for index, value in enumerate(fused)},
            })
    return rows


def summarize_detection(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, float], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["layout"], row["benchmark"], row["snr_db"])].append(row)
    summary = []
    for (layout, benchmark, snr_db), group in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][0], item[0][2])):
        signal_rows = [row for row in group if row["trial_type"] == "signal"]
        noise_rows = [row for row in group if row["trial_type"] == "noise"]
        fault_rates = _fault_rates(signal_rows)
        regions = group[0]["regions"] if group else ""
        summary.append({
            "layout": layout,
            "regions": regions,
            "benchmark": benchmark,
            "snr_db": snr_db,
            "signal_runs": len(signal_rows),
            "false_alarm_runs": len(noise_rows),
            "pd_any": _mean_bool(signal_rows, "detected_any"),
            "pd_all": _mean_bool(signal_rows, "detected_all"),
            "pd_source_mean": float(np.mean(fault_rates)) if fault_rates else float("nan"),
            "pd_source_min": float(np.min(fault_rates)) if fault_rates else float("nan"),
            "pd_source_variance": float(np.var(fault_rates)) if fault_rates else float("nan"),
            "p_fa": _mean_bool(noise_rows, "false_alarm"),
        })
    return summary


def run_experiments(
    cfg: Q4V1Config,
    grid_size: int,
    top_layouts: int,
    runs: int,
    false_alarm_runs: int,
    snr_levels: tuple[float, ...] = SNR_LEVELS,
    profile: str = "smoke",
) -> dict:
    started = time.perf_counter()
    points = generate_candidate_points(grid_size, cfg.random_seed)
    candidate_indexes, prescreen_rows = prescreen_points(points, cfg)
    greedy = greedy_layout(points, candidate_indexes, cfg=cfg)
    swapped = one_swap_search(points, candidate_indexes, greedy, cfg)
    exhaustive = exhaustive_layouts(points, candidate_indexes, max(top_layouts, 10), cfg)
    if not exhaustive:
        raise ValueError("Q4 V1 exhaustive search returned no layouts")
    best = exhaustive[0]
    gap = max(0.0, (best.objective - swapped.objective) / max(abs(best.objective), np.finfo(float).eps))

    baselines = baseline_layouts(points, candidate_indexes, cfg.random_seed)
    baseline_evals = {label: evaluate_layout(points, layout, cfg) for label, layout in baselines.items()}
    selected_evals = exhaustive[:top_layouts]
    for label, evaluation in baseline_evals.items():
        if layout_name(points, evaluation.layout) not in {layout_name(points, item.layout) for item in selected_evals}:
            selected_evals.append(evaluation)
    selected_evals.sort(key=lambda item: item.objective, reverse=True)
    benchmark_map = {layout_name(points, evaluation.layout): label for label, evaluation in baseline_evals.items()}
    benchmark_map[layout_name(points, best.layout)] = "v1_adaptive_best"

    trial_rows: list[dict] = []
    for evaluation in selected_evals:
        label = benchmark_map.get(layout_name(points, evaluation.layout), "v1_adaptive_candidate")
        trial_rows.extend(_run_detection_trials(points, evaluation.layout, label, snr_levels, runs, false_alarm_runs, cfg))

    detection_summary = summarize_detection(trial_rows)
    mesh_rows = [{
        "profile": profile,
        "grid_size": grid_size,
        "candidate_count": len(points),
        "prescreen_count": len(candidate_indexes),
        "greedy_layout": layout_name(points, greedy.layout),
        "greedy_objective": greedy.objective,
        "swap_layout": layout_name(points, swapped.layout),
        "swap_objective": swapped.objective,
        "exhaustive_best_layout": layout_name(points, best.layout),
        "exhaustive_best_objective": best.objective,
        "greedy_swap_gap_to_exhaustive": float(gap),
        "exhaustive_combo_count": math.comb(len(candidate_indexes), 3) if len(candidate_indexes) >= 3 else 0,
    }]
    return {
        "version": "q4_v1",
        "profile": profile,
        "config": cfg,
        "grid_size": grid_size,
        "top_layouts": top_layouts,
        "runs": runs,
        "false_alarm_runs": false_alarm_runs,
        "snr_levels": snr_levels,
        "points": points,
        "candidate_rows": _candidate_rows(points),
        "prescreen_rows": prescreen_rows,
        "selected_layout_rows": _layout_rows(points, selected_evals, benchmark_map),
        "mesh_rows": mesh_rows,
        "detection_summary": detection_summary,
        "trial_rows": trial_rows,
        "runtime_seconds": time.perf_counter() - started,
    }
