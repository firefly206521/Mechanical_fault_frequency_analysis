"""Monte Carlo experiments for Q4 sensor layout optimization."""

from __future__ import annotations

import time
from collections import defaultdict

import numpy as np

from .core import (
    DEFAULT_AMPLITUDES,
    DEFAULT_FREQUENCIES,
    FAULT_LABELS,
    SENSOR_NAMES,
    Q4Config,
    all_layouts,
    basis_matrices,
    base_sensitivity_matrix,
    default_scenarios,
    default_time_axis,
    evaluate_detection_trial,
    evaluate_false_alarm_trial,
    score_layout,
)


SNR_LEVELS = (-25.0, -20.0, -15.0, -12.0, -10.0, -5.0)


def _mean_bool(rows: list[dict], key: str) -> float:
    if not rows:
        return float("nan")
    return float(np.mean([bool(row[key]) for row in rows]))


def _fault_detection_rates(rows: list[dict]) -> list[float]:
    return [_mean_bool(rows, f"fault_{index + 1}_detected") for index in range(len(FAULT_LABELS))]


def summarize_rows(rows: list[dict], false_rows: list[dict], cfg: Q4Config) -> tuple[list[dict], list[dict], list[dict]]:
    grouped: dict[tuple[str, float], list[dict]] = defaultdict(list)
    false_grouped: dict[tuple[str, float], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["layout"], row["snr_db"])].append(row)
    for row in false_rows:
        false_grouped[(row["layout"], row["snr_db"])].append(row)

    snr_summary = []
    for (layout, snr_db), group in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        fgroup = false_grouped.get((layout, snr_db), [])
        fault_rates = _fault_detection_rates(group)
        p_fa = _mean_bool(fgroup, "false_alarm") if fgroup else float("nan")
        snr_summary.append({
            "layout": layout,
            "sensor_count": int(group[0]["sensor_count"]),
            "snr_db": snr_db,
            "runs": len(group),
            "pd_any": _mean_bool(group, "detected_any"),
            "pd_all": _mean_bool(group, "detected_all"),
            "pd_source_mean": float(np.mean(fault_rates)),
            "pd_source_min": float(np.min(fault_rates)),
            "pd_source_variance": float(np.var(fault_rates)),
            "false_alarm_runs": len(fgroup),
            "p_fa": p_fa,
            "score": score_layout(float(np.mean(fault_rates)), p_fa if np.isfinite(p_fa) else 0.0, fault_rates, cfg),
        })

    by_layout: dict[str, list[dict]] = defaultdict(list)
    for row in snr_summary:
        by_layout[row["layout"]].append(row)
    layout_ranking = []
    for layout, group in by_layout.items():
        if int(group[0]["sensor_count"]) > 3:
            continue
        low_snr_group = [row for row in group if row["snr_db"] <= -12.0]
        source_rates = [row["pd_source_mean"] for row in group]
        pfa_values = [row["p_fa"] for row in group if np.isfinite(row["p_fa"])]
        layout_ranking.append({
            "rank": 0,
            "layout": layout,
            "sensor_count": int(group[0]["sensor_count"]),
            "mean_pd_source": float(np.mean(source_rates)),
            "low_snr_pd_source": float(np.mean([row["pd_source_mean"] for row in low_snr_group])) if low_snr_group else float("nan"),
            "mean_pd_all": float(np.mean([row["pd_all"] for row in group])),
            "mean_p_fa": float(np.mean(pfa_values)) if pfa_values else float("nan"),
            "mean_balance_variance": float(np.mean([row["pd_source_variance"] for row in group])),
            "score": float(np.mean([row["score"] for row in group])),
        })
    layout_ranking.sort(key=lambda row: row["score"], reverse=True)
    for index, row in enumerate(layout_ranking, 1):
        row["rank"] = index

    coverage_rows = []
    best_layout = layout_ranking[0]["layout"] if layout_ranking else ""
    for snr_db in sorted({key[1] for key in grouped}):
        group = grouped.get((best_layout, snr_db), [])
        fault_rates = _fault_detection_rates(group)
        for index, label in enumerate(FAULT_LABELS):
            coverage_rows.append({
                "layout": best_layout,
                "scenario": "all_scenarios_mean",
                "scenario_count": len({row["scenario"] for row in group}),
                "snr_db": snr_db,
                "fault_label": label,
                "frequency_hz": float(DEFAULT_FREQUENCIES[index]),
                "amplitude": float(DEFAULT_AMPLITUDES[index]),
                "pd": fault_rates[index],
            })
    return snr_summary, layout_ranking, coverage_rows


def benchmark_layout_names(layout_ranking: list[dict]) -> dict[str, str]:
    if not layout_ranking:
        return {}
    single = next((row for row in layout_ranking if row["sensor_count"] == 1), None)
    best_three = next((row for row in layout_ranking if row["sensor_count"] == 3), None)
    full = "+".join(SENSOR_NAMES)
    random_three = "bearing_left+gearbox_right+input_shaft"
    selected = {
        "all_sensors_reference": full,
    }
    if single is not None:
        selected["single_best"] = single["layout"]
    if best_three is not None:
        selected["random_three"] = random_three
        selected["best_three"] = best_three["layout"]
    return selected


def run_experiments(
    cfg: Q4Config,
    runs: int,
    false_alarm_runs: int,
    snr_levels: tuple[float, ...] = SNR_LEVELS,
    scenario_names: tuple[str, ...] | None = None,
) -> dict:
    started = time.perf_counter()
    scenarios = default_scenarios()
    if scenario_names:
        requested = set(scenario_names)
        scenarios = [scenario for scenario in scenarios if scenario.name in requested]
        missing = sorted(requested - {scenario.name for scenario in scenarios})
        if missing:
            raise ValueError(f"Unknown Q4 scenario name(s): {', '.join(missing)}")
    layouts = all_layouts(max_sensors=3) + [tuple(SENSOR_NAMES)]
    detection_rows = []
    false_rows = []
    t = default_time_axis(cfg)
    sin_basis, cos_basis = basis_matrices(t, DEFAULT_FREQUENCIES)
    for scenario in scenarios:
        for layout in layouts:
            for snr_db in snr_levels:
                for replicate in range(runs):
                    detection_rows.append(evaluate_detection_trial(
                        layout, scenario, snr_db, replicate, cfg, t=t, sin_basis=sin_basis, cos_basis=cos_basis
                    ))
                for replicate in range(false_alarm_runs):
                    false_rows.append(evaluate_false_alarm_trial(
                        layout, scenario, snr_db, replicate, cfg, t=t, sin_basis=sin_basis, cos_basis=cos_basis
                    ))
    snr_summary, layout_ranking, coverage_rows = summarize_rows(detection_rows, false_rows, cfg)
    selected = benchmark_layout_names(layout_ranking)
    selected_rows = [
        {**row, "benchmark": label}
        for label, layout in selected.items()
        for row in snr_summary
        if row["layout"] == layout
    ]
    robustness_rows = []
    for scenario in scenarios:
        scenario_rows = [row for row in detection_rows if row["scenario"] == scenario.name]
        scenario_false = [row for row in false_rows if row["scenario"] == scenario.name]
        scenario_summary, scenario_ranking, _ = summarize_rows(scenario_rows, scenario_false, cfg)
        best = scenario_ranking[0]
        robustness_rows.append({
            "scenario": scenario.name,
            "description": scenario.description,
            "best_layout": best["layout"],
            "best_score": best["score"],
            "best_low_snr_pd_source": best["low_snr_pd_source"],
            "best_mean_p_fa": best["mean_p_fa"],
        })
    return {
        "config": cfg,
        "scenarios": scenarios,
        "sensitivity_matrix": base_sensitivity_matrix(),
        "detection_rows": detection_rows,
        "false_alarm_rows": false_rows,
        "snr_summary": snr_summary,
        "layout_ranking": layout_ranking,
        "coverage_rows": coverage_rows,
        "selected_snr_rows": selected_rows,
        "robustness_rows": robustness_rows,
        "runtime_seconds": time.perf_counter() - started,
        "runs": runs,
        "false_alarm_runs": false_alarm_runs,
        "snr_levels": snr_levels,
        "scenario_names": tuple(scenario.name for scenario in scenarios),
    }
