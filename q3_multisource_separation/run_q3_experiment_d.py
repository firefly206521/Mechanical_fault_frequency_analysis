"""Experiment D: conditional close-frequency performance surface for Q3.

The review issue asks to replace a single "resolution limit" number with an
empirical surface conditioned on observation length, weak-component SNR,
amplitude ratio, and random phase. This runner keeps the Q3 detector unchanged
and only adds a reproducible Monte Carlo harness plus paper/raw outputs.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Callable

import numpy as np

from . import SEED
from .core import GLRTConfig, close_pair_resolver, detect_multitone, q1_compatible_glrt_threshold
from .experiments import wilson_interval
from q2_harmonic_recovery.outputs import line_svg
from q3_multisource_separation.outputs import convert_q3_svg_plots_to_png


SNR_LEVELS_DB = (-6.0, -12.0, -18.0)
AMPLITUDE_RATIOS = (1, 3, 10)
SEPARATIONS_HZ = (0.001, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.008, 0.010, 0.015, 0.020)
PHASE_BINS = 8

_WORKER_T = None
_WORKER_CENTER_HZ = None
_WORKER_WEAK_AMPLITUDE = None
_WORKER_GRID_STEP_HZ = None
_WORKER_CONDITIONAL_THRESHOLD = None
_WORKER_DETECTOR = None
_WORKER_FS = None
_WORKER_CFG = None
_WORKER_MAX_COMPONENTS = None
_WORKER_BIC_DELTA = None


def _rng(experiment_id: int, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, 47, experiment_id, replicate]))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _append_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    fieldnames = list(rows[0].keys())
    if exists:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            existing = next(csv.reader(handle), None)
        if existing != fieldnames:
            raise ValueError(f"CSV schema mismatch for {path}: existing={existing}, new={fieldnames}")
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _init_worker(t, fs, center_hz, weak_amplitude, grid_step_hz, conditional_threshold, detector, cfg, max_components, bic_delta) -> None:
    global _WORKER_T, _WORKER_FS, _WORKER_CENTER_HZ, _WORKER_WEAK_AMPLITUDE, _WORKER_GRID_STEP_HZ
    global _WORKER_CONDITIONAL_THRESHOLD, _WORKER_DETECTOR, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA
    _WORKER_T = t
    _WORKER_FS = fs
    _WORKER_CENTER_HZ = center_hz
    _WORKER_WEAK_AMPLITUDE = weak_amplitude
    _WORKER_GRID_STEP_HZ = grid_step_hz
    _WORKER_CONDITIONAL_THRESHOLD = conditional_threshold
    _WORKER_DETECTOR = detector
    _WORKER_CFG = cfg
    _WORKER_MAX_COMPONENTS = max_components
    _WORKER_BIC_DELTA = bic_delta


def _signal(t: np.ndarray, frequencies: np.ndarray, amplitudes: np.ndarray, phases: np.ndarray) -> np.ndarray:
    return np.sum(
        [a * np.sin(2.0 * np.pi * f * t + p) for a, f, p in zip(amplitudes, frequencies, phases)],
        axis=0,
    )


def _phase_difference(phases: np.ndarray) -> float:
    value = abs(float(np.angle(np.exp(1j * (phases[1] - phases[0])))))
    return min(value, 2.0 * math.pi - value)


def _match_max_error(estimated: np.ndarray, truth: np.ndarray) -> float:
    estimated = list(np.sort(np.asarray(estimated, float)))
    truth = np.sort(np.asarray(truth, float))
    if len(estimated) != len(truth):
        return float("nan")
    errors = []
    for value in truth:
        index = int(np.argmin(np.abs(np.asarray(estimated) - value)))
        errors.append(abs(estimated.pop(index) - value))
    return float(max(errors))


def _trial_worker(task: tuple[float, int, float, int]) -> dict:
    snr_db, amplitude_ratio, separation_hz, replicate = task
    ratio_index = AMPLITUDE_RATIOS.index(amplitude_ratio)
    sep_index = SEPARATIONS_HZ.index(separation_hz)
    snr_index = SNR_LEVELS_DB.index(snr_db)
    rng = _rng(1000 + 100 * snr_index + 10 * ratio_index + sep_index, replicate)
    weak_amplitude = float(_WORKER_WEAK_AMPLITUDE)
    amplitudes = np.asarray([weak_amplitude, weak_amplitude * amplitude_ratio], dtype=float)
    frequencies = np.asarray([
        _WORKER_CENTER_HZ - separation_hz / 2.0,
        _WORKER_CENTER_HZ + separation_hz / 2.0,
    ])
    phases = rng.uniform(-np.pi, np.pi, 2)
    weak_power = weak_amplitude ** 2 / 2.0
    noise_std = math.sqrt(weak_power / (10.0 ** (snr_db / 10.0)))
    observed = _signal(_WORKER_T, frequencies, amplitudes, phases) + rng.normal(0.0, noise_std, len(_WORKER_T))

    started = time.perf_counter()
    if _WORKER_DETECTOR == "complete":
        fit, history = detect_multitone(
            _WORKER_T,
            observed,
            _WORKER_FS,
            _WORKER_CFG,
            max_components=_WORKER_MAX_COMPONENTS,
            bic_delta=_WORKER_BIC_DELTA,
        )
        estimated_k = int(len(fit["frequencies_hz"]))
        last_accept = next((row for row in reversed(history) if row.get("accepted")), {})
        candidate_origin = last_accept.get("candidate_origin", "")
        bic_improvement = float(last_accept.get("bic_improvement", float("nan")))
        conditional_statistic = float("nan")
        conditional_threshold = float("nan")
    else:
        fit = close_pair_resolver(
            _WORKER_T,
            observed,
            center_hz=_WORKER_CENTER_HZ,
            local_grid_step_hz=_WORKER_GRID_STEP_HZ,
            conditional_threshold=_WORKER_CONDITIONAL_THRESHOLD,
        )
        estimated_k = int(fit["estimated_k"])
        candidate_origin = fit.get("candidate_origin", "")
        bic_improvement = float(fit.get("bic_improvement", float("nan")))
        conditional_statistic = float(fit.get("conditional_glrt_statistic", float("nan")))
        conditional_threshold = float(fit.get("conditional_glrt_threshold", float("nan")))
    elapsed = time.perf_counter() - started
    estimated = np.asarray(fit["frequencies_hz"], float)
    tolerance = separation_hz / 4.0
    max_error = _match_max_error(estimated, frequencies)
    success = bool(
        estimated_k == 2
        and math.isfinite(max_error)
        and max_error <= tolerance
        and not fit["ill_conditioned"]
    )
    phase_diff = _phase_difference(phases)
    phase_bin = min(PHASE_BINS - 1, int(phase_diff / math.pi * PHASE_BINS))
    return {
        "snr_weak_db": snr_db,
        "amplitude_ratio_weak_to_strong": f"1:{amplitude_ratio}",
        "amplitude_ratio_value": amplitude_ratio,
        "separation_hz": separation_hz,
        "replicate": replicate,
        "center_hz": _WORKER_CENTER_HZ,
        "true_frequency_1_hz": frequencies[0],
        "true_frequency_2_hz": frequencies[1],
        "weak_amplitude": amplitudes[0],
        "strong_amplitude": amplitudes[1],
        "noise_std": noise_std,
        "phase_1_rad": phases[0],
        "phase_2_rad": phases[1],
        "phase_difference_abs_rad": phase_diff,
        "phase_bin": phase_bin,
        "detector": _WORKER_DETECTOR,
        "estimated_k": estimated_k,
        "success": success,
        "max_frequency_error_hz": max_error,
        "tolerance_hz": tolerance,
        "estimated_frequencies_hz": ";".join(f"{value:.12g}" for value in estimated),
        "bic_improvement": bic_improvement,
        "candidate_origin": candidate_origin,
        "conditional_glrt_statistic": conditional_statistic,
        "conditional_glrt_threshold": conditional_threshold,
        "condition_design": float(fit["condition_design"]),
        "ill_conditioned": bool(fit["ill_conditioned"]),
        "runtime_seconds": elapsed,
    }


def _run_stage(tasks: list[tuple[float, int, float, int]], worker: Callable, workers: int, path: Path) -> list[dict]:
    existing_rows = _read_csv(path)
    existing = {
        (float(row["snr_weak_db"]), int(float(row["amplitude_ratio_value"])), float(row["separation_hz"]), int(row["replicate"]))
        for row in existing_rows
    }
    pending = [task for task in tasks if task not in existing]
    if not pending:
        return existing_rows
    started = time.perf_counter()
    new_rows = []
    buffer = []

    def record(row: dict, count: int) -> None:
        new_rows.append(row)
        buffer.append(row)
        if len(buffer) >= 25 or count == len(pending):
            _append_csv(path, buffer)
            buffer.clear()
        if count % 25 == 0 or count == len(pending):
            elapsed = time.perf_counter() - started
            rate = elapsed / max(count, 1)
            remain = rate * (len(pending) - count)
            print(f"实验D-条件化近频曲面: {count}/{len(pending)}; elapsed={elapsed:.1f}s; remaining≈{remain:.1f}s", flush=True)

    if workers <= 1:
        for count, task in enumerate(pending, 1):
            record(worker(task), count)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(
                _WORKER_T,
                _WORKER_FS,
                _WORKER_CENTER_HZ,
                _WORKER_WEAK_AMPLITUDE,
                _WORKER_GRID_STEP_HZ,
                _WORKER_CONDITIONAL_THRESHOLD,
                _WORKER_DETECTOR,
                _WORKER_CFG,
                _WORKER_MAX_COMPONENTS,
                _WORKER_BIC_DELTA,
            ),
        ) as pool:
            for count, row in enumerate(pool.map(worker, pending), 1):
                record(row, count)
    return existing_rows + new_rows


def _summarize_surface(rows: list[dict]) -> list[dict]:
    summary = []
    for snr_db in SNR_LEVELS_DB:
        for ratio in AMPLITUDE_RATIOS:
            for separation in SEPARATIONS_HZ:
                group = [
                    row for row in rows
                    if float(row["snr_weak_db"]) == snr_db
                    and int(float(row["amplitude_ratio_value"])) == ratio
                    and abs(float(row["separation_hz"]) - separation) < 1e-12
                ]
                successes = sum(str(row["success"]).lower() == "true" for row in group)
                low, high = wilson_interval(successes, len(group)) if group else (float("nan"), float("nan"))
                errors = [float(row["max_frequency_error_hz"]) for row in group if str(row["success"]).lower() == "true"]
                summary.append({
                    "snr_weak_db": snr_db,
                    "amplitude_ratio_weak_to_strong": f"1:{ratio}",
                    "amplitude_ratio_value": ratio,
                    "separation_hz": separation,
                    "rayleigh_multiples": separation * 400.0,
                    "runs": len(group),
                    "successes": successes,
                    "success_rate": successes / len(group) if group else float("nan"),
                    "success_ci95_low": low,
                    "success_ci95_high": high,
                    "mean_max_frequency_error_hz_if_success": float(np.mean(errors)) if errors else float("nan"),
                    "median_condition_design": float(np.median([float(row["condition_design"]) for row in group])) if group else float("nan"),
                    "ill_conditioned_rate": sum(str(row["ill_conditioned"]).lower() == "true" for row in group) / len(group) if group else float("nan"),
                    "mean_runtime_seconds": float(np.mean([float(row["runtime_seconds"]) for row in group])) if group else float("nan"),
                })
    return summary


def _summarize_phase(rows: list[dict]) -> list[dict]:
    summary = []
    for snr_db in SNR_LEVELS_DB:
        for ratio in AMPLITUDE_RATIOS:
            for separation in SEPARATIONS_HZ:
                group = [
                    row for row in rows
                    if float(row["snr_weak_db"]) == snr_db
                    and int(float(row["amplitude_ratio_value"])) == ratio
                    and abs(float(row["separation_hz"]) - separation) < 1e-12
                ]
                if not group:
                    continue
                average = sum(str(row["success"]).lower() == "true" for row in group) / len(group)
                bin_rates = []
                for phase_bin in range(PHASE_BINS):
                    bin_group = [row for row in group if int(row["phase_bin"]) == phase_bin]
                    if len(bin_group) >= 5:
                        bin_rates.append(sum(str(row["success"]).lower() == "true" for row in bin_group) / len(bin_group))
                summary.append({
                    "snr_weak_db": snr_db,
                    "amplitude_ratio_weak_to_strong": f"1:{ratio}",
                    "amplitude_ratio_value": ratio,
                    "separation_hz": separation,
                    "runs": len(group),
                    "random_phase_average_success_rate": average,
                    "worst_phase_bin_success_rate": min(bin_rates) if bin_rates else float("nan"),
                    "best_phase_bin_success_rate": max(bin_rates) if bin_rates else float("nan"),
                    "phase_bin_count_used": len(bin_rates),
                })
    return summary


def _empirical_limit(summary: list[dict], snr_db: float, ratio: int, target: float) -> float:
    rows = [
        row for row in sorted(summary, key=lambda item: float(item["separation_hz"]))
        if float(row["snr_weak_db"]) == snr_db and int(float(row["amplitude_ratio_value"])) == ratio
    ]
    for index, row in enumerate(rows):
        tail = rows[index:]
        if tail and all(float(item["success_rate"]) >= target for item in tail):
            return float(row["separation_hz"])
    return float("nan")


def _summarize_limits(summary: list[dict], target: float) -> list[dict]:
    rows = []
    for snr_db in SNR_LEVELS_DB:
        for ratio in AMPLITUDE_RATIOS:
            rows.append({
                "snr_weak_db": snr_db,
                "amplitude_ratio_weak_to_strong": f"1:{ratio}",
                "amplitude_ratio_value": ratio,
                "success_standard": target,
                "empirical_resolution_limit_hz": _empirical_limit(summary, snr_db, ratio, target),
            })
    return rows


def _write_plots(paper_dir: Path, surface: list[dict], phase: list[dict]) -> list[Path]:
    colors = {
        (-6.0, 1): "#1f77b4",
        (-6.0, 3): "#2ca02c",
        (-6.0, 10): "#17becf",
        (-12.0, 1): "#ff7f0e",
        (-12.0, 3): "#9467bd",
        (-12.0, 10): "#bcbd22",
        (-18.0, 1): "#d62728",
        (-18.0, 3): "#8c564b",
        (-18.0, 10): "#7f7f7f",
    }
    series = []
    for snr_db in SNR_LEVELS_DB:
        for ratio in AMPLITUDE_RATIOS:
            rows = [
                row for row in surface
                if float(row["snr_weak_db"]) == snr_db and int(float(row["amplitude_ratio_value"])) == ratio
            ]
            rows.sort(key=lambda row: float(row["separation_hz"]))
            series.append((
                f"SNR {snr_db:g} dB，幅比1:{ratio}",
                [float(row["separation_hz"]) for row in rows],
                [float(row["success_rate"]) for row in rows],
                colors[(snr_db, ratio)],
            ))
    line_svg(
        paper_dir / "q3_experiment_d_success_surface.svg",
        "Q3 条件化近频辨识成功率",
        "频率间隔 Δf (Hz)",
        "成功率",
        series,
    )

    phase_series = []
    for snr_db, ratio in [(-6.0, 1), (-12.0, 3), (-18.0, 10)]:
        rows = [
            row for row in phase
            if float(row["snr_weak_db"]) == snr_db and int(float(row["amplitude_ratio_value"])) == ratio
        ]
        rows.sort(key=lambda row: float(row["separation_hz"]))
        phase_series.append((
            f"平均 SNR {snr_db:g} dB 幅比1:{ratio}",
            [float(row["separation_hz"]) for row in rows],
            [float(row["random_phase_average_success_rate"]) for row in rows],
            colors[(snr_db, ratio)],
        ))
        phase_series.append((
            f"最不利相位分箱 SNR {snr_db:g} dB 幅比1:{ratio}",
            [float(row["separation_hz"]) for row in rows],
            [float(row["worst_phase_bin_success_rate"]) for row in rows],
            "#000000",
        ))
    line_svg(
        paper_dir / "q3_experiment_d_phase_effect.svg",
        "Q3 随机相位平均与最不利相位分箱",
        "频率间隔 Δf (Hz)",
        "成功率",
        phase_series,
    )
    return convert_q3_svg_plots_to_png(paper_dir, remove_svg=True)


def _write_report(path: Path, context: dict) -> None:
    lines = [
        "# Q3 实验 D：条件化近频辨识性能曲面",
        "",
        "本实验用于替换单一“辨识极限”数字。近频辨识能力写作经验函数：",
        "",
        "`P_success = g(T, SNR_weak, A_weak:A_strong, Δf, Δφ)`。",
        "",
        "## 参数",
        "",
        f"- 记录长度 T={context['duration_s']:.3f} s，样本数 N={context['sample_count']}，采样率 fs={context['fs_hz']} Hz。",
        f"- 中心频率 {context['center_hz']} Hz，频率对为 `center ± Δf/2`。",
        f"- 检测器：{context['detector']}。",
        f"- 弱分量幅值 {context['weak_amplitude']}，强分量按 1:1、1:3、1:10 放大。",
        f"- SNR 以较弱分量计：{', '.join(f'{value:g} dB' for value in SNR_LEVELS_DB)}。",
        f"- 每格 Monte Carlo {context['runs_per_cell']} 次，随机相位服从均匀分布。",
        f"- 成功标准：自动识别两个分量，两个频率最大误差不超过 `Δf/4`，且未被标记为病态。",
        f"- 90% 成功率经验界限按“该间隔及更大间隔均不低于 90%”定义。",
        "",
        "## 90% 经验辨识界限",
        "",
        "| 弱分量SNR/dB | 振幅比 | 90%经验界限/Hz |",
        "|---:|---:|---:|",
    ]
    for row in context["limit_summary"]:
        value = float(row["empirical_resolution_limit_hz"])
        text = f"{value:.6g}" if math.isfinite(value) else "未达到"
        lines.append(f"| {row['snr_weak_db']:.0f} | {row['amplitude_ratio_weak_to_strong']} | {text} |")
    lines += [
        "",
        "## 性能曲面摘要",
        "",
        "| 弱分量SNR/dB | 振幅比 | Δf/Hz | 重复次数 | 成功率 | 95% CI | 病态率 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in context["surface_summary"]:
        lines.append(
            f"| {row['snr_weak_db']:.0f} | {row['amplitude_ratio_weak_to_strong']} | "
            f"{row['separation_hz']:.6g} | {row['runs']} | {row['success_rate']:.1%} | "
            f"[{row['success_ci95_low']:.1%}, {row['success_ci95_high']:.1%}] | {row['ill_conditioned_rate']:.1%} |"
        )
    lines += [
        "",
        "## 相位影响",
        "",
        "辅助表把相位差折叠到 `[0, π]` 并分为 8 个分箱；每个条件下报告随机相位平均成功率、最不利相位分箱成功率和最好分箱成功率。最不利分箱是经验诊断，不是严格理论下界。",
        "",
        "## 结论口径",
        "",
        "论文中不应把 0.0025 Hz 写成算法固定理论极限。更合适的表述是：在 T=400 s、给定弱分量 SNR、振幅比和随机相位分布下，按 90% 成功率标准得到对应的经验辨识界限。完全同频、严重相消或更低 SNR 下的边界必须另行条件化说明。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Q3 Experiment D conditional close-frequency performance surface.")
    parser.add_argument("--output-dir", type=Path, default=Path("q3_experiment_d_results"))
    parser.add_argument("--profile", choices=("smoke", "official"), default="official")
    parser.add_argument("--sample-count", type=int, default=40001)
    parser.add_argument("--fs", type=float, default=100.0)
    parser.add_argument("--center-hz", type=float, default=5.0)
    parser.add_argument("--weak-amplitude", type=float, default=0.01)
    parser.add_argument("--runs", type=int, default=None)
    parser.add_argument("--grid-step-hz", type=float, default=0.00025)
    parser.add_argument("--conditional-threshold", type=float, default=None)
    parser.add_argument("--detector", choices=("complete", "close_pair"), default="complete")
    parser.add_argument("--glrt-mc", type=int, default=500)
    parser.add_argument("--max-components", type=int, default=4)
    parser.add_argument("--bic-delta", type=float, default=10.0)
    parser.add_argument("--target-success", type=float, default=0.90)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    return parser.parse_args()


def main() -> None:
    global _WORKER_T, _WORKER_FS, _WORKER_CENTER_HZ, _WORKER_WEAK_AMPLITUDE, _WORKER_GRID_STEP_HZ
    global _WORKER_CONDITIONAL_THRESHOLD, _WORKER_DETECTOR, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA
    args = parse_args()
    default_runs = {"smoke": 3, "official": 200}[args.profile]
    runs = args.runs if args.runs is not None else default_runs
    if min(args.sample_count, runs, args.workers) < 1:
        raise ValueError("sample-count, runs, and workers must be positive")
    if not (0.0 < args.target_success <= 1.0):
        raise ValueError("target-success must be in (0, 1]")

    output_dir = args.output_dir.resolve()
    paper_dir = output_dir / "paper"
    raw_dir = output_dir / "raw"
    paper_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    _WORKER_T = np.arange(args.sample_count, dtype=float) / args.fs
    _WORKER_FS = args.fs
    _WORKER_CENTER_HZ = args.center_hz
    _WORKER_WEAK_AMPLITUDE = args.weak_amplitude
    _WORKER_GRID_STEP_HZ = args.grid_step_hz
    _WORKER_CONDITIONAL_THRESHOLD = args.conditional_threshold
    _WORKER_DETECTOR = args.detector
    _WORKER_MAX_COMPONENTS = args.max_components
    _WORKER_BIC_DELTA = args.bic_delta
    cfg = GLRTConfig(
        f_min=0.05,
        f_max=min(49.5, args.fs / 2.0 - 0.5),
        p_fa=0.05 / args.max_components,
        glrt_mc=args.glrt_mc,
        random_seed=SEED,
    )
    threshold = q1_compatible_glrt_threshold(args.sample_count, args.fs, cfg)
    _WORKER_CFG = replace(cfg, threshold=threshold)

    tasks = [
        (snr_db, ratio, separation, replicate)
        for snr_db in SNR_LEVELS_DB
        for ratio in AMPLITUDE_RATIOS
        for separation in SEPARATIONS_HZ
        for replicate in range(runs)
    ]
    trial_path = raw_dir / "q3_experiment_d_trials.csv"
    rows = _run_stage(tasks, _trial_worker, max(1, args.workers), trial_path)

    surface_summary = _summarize_surface(rows)
    phase_summary = _summarize_phase(rows)
    limit_summary = _summarize_limits(surface_summary, args.target_success)
    _write_csv(paper_dir / "q3_experiment_d_success_surface.csv", surface_summary)
    _write_csv(paper_dir / "q3_experiment_d_resolution_limits.csv", limit_summary)
    _write_csv(paper_dir / "q3_experiment_d_phase_effect.csv", phase_summary)
    pngs = _write_plots(paper_dir, surface_summary, phase_summary)

    context = {
        "profile": args.profile,
        "sample_count": args.sample_count,
        "fs_hz": args.fs,
        "duration_s": float(_WORKER_T[-1] - _WORKER_T[0]),
        "center_hz": args.center_hz,
        "detector": args.detector,
        "weak_amplitude": args.weak_amplitude,
        "runs_per_cell": runs,
        "snr_levels_db": list(SNR_LEVELS_DB),
        "amplitude_ratios": [f"1:{value}" for value in AMPLITUDE_RATIOS],
        "separations_hz": list(SEPARATIONS_HZ),
        "phase_bins": PHASE_BINS,
        "grid_step_hz": args.grid_step_hz,
        "conditional_threshold": args.conditional_threshold,
        "glrt_mc": args.glrt_mc,
        "glrt_threshold": threshold,
        "max_components": args.max_components,
        "bic_delta": args.bic_delta,
        "target_success": args.target_success,
        "workers": max(1, args.workers),
        "seed": SEED,
        "runtime_seconds": time.perf_counter() - started,
        "paper_pngs": [str(path.name) for path in pngs],
        "surface_summary": surface_summary,
        "phase_summary": phase_summary,
        "limit_summary": limit_summary,
        "command": sys.argv,
    }
    _write_report(paper_dir / "q3_experiment_d_report.md", context)
    (raw_dir / "q3_experiment_d_runtime.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "README.md").write_text(
        "\n".join([
            "# Q3 Experiment D Results",
            "",
            "This directory contains the conditional close-frequency performance surface for Q3 issue #47.",
            "",
            "- `paper/`: paper-facing report, summary CSV tables, and figures.",
            "- `raw/`: trial-level Monte Carlo rows and runtime metadata.",
            "",
            f"Profile: `{args.profile}`.",
            "The result is an empirical conditional surface, not a theoretical global resolution limit.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"Experiment D complete: {output_dir}")


if __name__ == "__main__":
    main()
