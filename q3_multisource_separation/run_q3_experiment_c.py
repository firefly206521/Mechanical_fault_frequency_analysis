"""Experiment C: full SIC+BIC order calibration for Q3.

This runner is intentionally separate from ``run_q3.py`` because the review
issue asks for final-order calibration of the complete detector, not the
first-step GLRT null scan already present in the main Q3 run.
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
from .core import GLRTConfig, detect_multitone, q1_compatible_glrt_threshold
from .experiments import wilson_interval


DISTANCES_HZ = (0.5, 1.0, 2.0, 5.0)
ORDER_K_VALUES = (1, 2, 3, 4)

_WORKER_T = None
_WORKER_FS = None
_WORKER_CFG = None
_WORKER_MAX_COMPONENTS = None
_WORKER_BIC_DELTA = None
_WORKER_NOISE_STD = None


def _rng(experiment_id: int, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, 46, experiment_id, replicate]))


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


def _random_frequencies(rng: np.random.Generator, k: int, lo: float = 1.0, hi: float = 15.0, min_gap: float = 1.0) -> np.ndarray:
    for _ in range(10_000):
        frequencies = np.sort(rng.uniform(lo, hi, k))
        if k <= 1 or np.min(np.diff(frequencies)) >= min_gap:
            return frequencies
    raise RuntimeError(f"Could not sample {k} frequencies with min gap {min_gap} Hz")


def _signal(t: np.ndarray, frequencies: np.ndarray, amplitudes: np.ndarray, phases: np.ndarray) -> np.ndarray:
    return np.sum(
        [a * np.sin(2.0 * np.pi * f * t + p) for a, f, p in zip(amplitudes, frequencies, phases)],
        axis=0,
    )


def _match_mae(estimated: np.ndarray, truth: np.ndarray) -> float:
    estimated = list(np.sort(np.asarray(estimated, float)))
    truth = np.sort(np.asarray(truth, float))
    if not estimated or len(estimated) != len(truth):
        return float("nan")
    errors = []
    for value in truth:
        index = int(np.argmin(np.abs(np.asarray(estimated) - value)))
        errors.append(abs(estimated.pop(index) - value))
    return float(np.mean(errors))


def _fit_complete_flow(y: np.ndarray) -> tuple[dict, list[dict], float]:
    started = time.perf_counter()
    fit, history = detect_multitone(
        _WORKER_T,
        y,
        _WORKER_FS,
        _WORKER_CFG,
        max_components=_WORKER_MAX_COMPONENTS,
        bic_delta=_WORKER_BIC_DELTA,
    )
    return fit, history, time.perf_counter() - started


def _init_worker(t, fs, cfg, max_components, bic_delta, noise_std) -> None:
    global _WORKER_T, _WORKER_FS, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA, _WORKER_NOISE_STD
    _WORKER_T = t
    _WORKER_FS = fs
    _WORKER_CFG = cfg
    _WORKER_MAX_COMPONENTS = max_components
    _WORKER_BIC_DELTA = bic_delta
    _WORKER_NOISE_STD = noise_std


def _null_worker(replicate: int) -> dict:
    rng = _rng(1, replicate)
    y = rng.normal(0.0, _WORKER_NOISE_STD, len(_WORKER_T))
    fit, history, elapsed = _fit_complete_flow(y)
    estimated_k = int(len(fit["frequencies_hz"]))
    first = history[0] if history else {}
    return {
        "replicate": replicate,
        "sample_count": len(_WORKER_T),
        "true_k": 0,
        "estimated_k": estimated_k,
        "false_alarm_final": bool(estimated_k >= 1),
        "first_glrt_passed": bool(first.get("glrt_passed", False)),
        "first_glrt_score": float(first.get("glrt_score", float("nan"))),
        "first_glrt_threshold": float(first.get("glrt_threshold", float("nan"))),
        "accepted_iterations": sum(str(row.get("accepted")).lower() == "true" for row in history),
        "runtime_seconds": elapsed,
    }


def _order_worker(task: tuple[int, int]) -> dict:
    true_k, replicate = task
    rng = _rng(100 + true_k, replicate)
    frequencies = _random_frequencies(rng, true_k)
    amplitudes = rng.uniform(0.01, 0.1, true_k)
    phases = rng.uniform(-np.pi, np.pi, true_k)
    y = _signal(_WORKER_T, frequencies, amplitudes, phases) + rng.normal(0.0, _WORKER_NOISE_STD, len(_WORKER_T))
    fit, history, elapsed = _fit_complete_flow(y)
    estimated = np.asarray(fit["frequencies_hz"], float)
    estimated_k = int(len(estimated))
    return {
        "true_k": true_k,
        "replicate": replicate,
        "sample_count": len(_WORKER_T),
        "estimated_k": estimated_k,
        "under_estimated": bool(estimated_k < true_k),
        "correct_order": bool(estimated_k == true_k),
        "over_estimated": bool(estimated_k > true_k),
        "frequency_mae_hz_if_correct_k": _match_mae(estimated, frequencies),
        "amplitudes": ";".join(f"{value:.9g}" for value in amplitudes),
        "true_frequencies_hz": ";".join(f"{value:.9g}" for value in frequencies),
        "estimated_frequencies_hz": ";".join(f"{value:.9g}" for value in estimated),
        "accepted_iterations": sum(str(row.get("accepted")).lower() == "true" for row in history),
        "condition_design": float(fit["condition_design"]),
        "ill_conditioned": bool(fit["ill_conditioned"]),
        "runtime_seconds": elapsed,
    }


def _weak_strong_worker(task: tuple[float, int]) -> dict:
    distance_hz, replicate = task
    rng = _rng(200 + int(round(distance_hz * 10)), replicate)
    frequencies = np.asarray([3.0, 3.0 + distance_hz, 10.5, 14.0], dtype=float)
    amplitudes = np.asarray([0.005, *rng.uniform(0.03, 0.05, 3)], dtype=float)
    phases = rng.uniform(-np.pi, np.pi, 4)
    y = _signal(_WORKER_T, frequencies, amplitudes, phases) + rng.normal(0.0, _WORKER_NOISE_STD, len(_WORKER_T))
    fit, history, elapsed = _fit_complete_flow(y)
    estimated = np.asarray(fit["frequencies_hz"], float)
    weak_error = float(np.min(np.abs(estimated - frequencies[0]))) if len(estimated) else float("nan")
    strong_errors = []
    remaining = list(estimated)
    for value in frequencies[1:]:
        if not remaining:
            strong_errors.append(float("nan"))
            continue
        index = int(np.argmin(np.abs(np.asarray(remaining) - value)))
        strong_errors.append(abs(remaining.pop(index) - value))
    estimated_k = int(len(estimated))
    return {
        "weak_to_nearest_strong_distance_hz": distance_hz,
        "replicate": replicate,
        "sample_count": len(_WORKER_T),
        "true_k": 4,
        "estimated_k": estimated_k,
        "weak_detected": bool(np.isfinite(weak_error) and weak_error <= 0.02),
        "strong_components_detected": bool(all(np.isfinite(value) and value <= 0.02 for value in strong_errors)),
        "correct_order": bool(estimated_k == 4),
        "over_estimated": bool(estimated_k > 4),
        "weak_frequency_error_hz": weak_error,
        "strong_frequency_mae_hz": float(np.nanmean(strong_errors)),
        "strong_amplitudes": ";".join(f"{value:.9g}" for value in amplitudes[1:]),
        "estimated_frequencies_hz": ";".join(f"{value:.9g}" for value in estimated),
        "accepted_iterations": sum(str(row.get("accepted")).lower() == "true" for row in history),
        "condition_design": float(fit["condition_design"]),
        "ill_conditioned": bool(fit["ill_conditioned"]),
        "runtime_seconds": elapsed,
    }


def _run_stage(label: str, tasks: list, worker: Callable, workers: int, path: Path, key: Callable[[dict], tuple]) -> list[dict]:
    existing_rows = _read_csv(path)
    existing = {key(row) for row in existing_rows}
    pending = [task for task in tasks if task not in existing]
    if not pending:
        return existing_rows
    started = time.perf_counter()
    new_rows = []
    buffer = []

    def record(row: dict, count: int) -> None:
        new_rows.append(row)
        buffer.append(row)
        if len(buffer) >= 20 or count == len(pending):
            _append_csv(path, buffer)
            buffer.clear()
        if count % 20 == 0 or count == len(pending):
            elapsed = time.perf_counter() - started
            rate = elapsed / max(count, 1)
            remain = rate * (len(pending) - count)
            print(f"{label}: {count}/{len(pending)}; elapsed={elapsed:.1f}s; remaining≈{remain:.1f}s", flush=True)

    if workers <= 1:
        for count, task in enumerate(pending, 1):
            record(worker(task), count)
    else:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(_WORKER_T, _WORKER_FS, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA, _WORKER_NOISE_STD),
        ) as pool:
            for count, row in enumerate(pool.map(worker, pending), 1):
                record(row, count)
    return existing_rows + new_rows


def _rate_row(label: str, rows: list[dict], predicate: Callable[[dict], bool]) -> dict:
    runs = len(rows)
    successes = sum(predicate(row) for row in rows)
    low, high = wilson_interval(successes, runs) if runs else (float("nan"), float("nan"))
    return {
        "case": label,
        "runs": runs,
        "count": successes,
        "rate": successes / runs if runs else float("nan"),
        "ci95_low": low,
        "ci95_high": high,
    }


def _summarize_null(rows: list[dict]) -> list[dict]:
    return [_rate_row("K=0 pure noise final false alarm P(K_hat>=1)", rows, lambda row: str(row["false_alarm_final"]).lower() == "true")]


def _summarize_order(rows: list[dict]) -> list[dict]:
    summary = []
    for true_k in ORDER_K_VALUES:
        group = [row for row in rows if int(row["true_k"]) == true_k]
        under = sum(int(row["estimated_k"]) < true_k for row in group)
        equal = sum(int(row["estimated_k"]) == true_k for row in group)
        over = sum(int(row["estimated_k"]) > true_k for row in group)
        low, high = wilson_interval(equal, len(group)) if group else (float("nan"), float("nan"))
        correct_errors = [float(row["frequency_mae_hz_if_correct_k"]) for row in group if str(row["correct_order"]).lower() == "true" and math.isfinite(float(row["frequency_mae_hz_if_correct_k"]))]
        summary.append({
            "true_k": true_k,
            "runs": len(group),
            "under_estimation_rate": under / len(group) if group else float("nan"),
            "correct_order_rate": equal / len(group) if group else float("nan"),
            "correct_ci95_low": low,
            "correct_ci95_high": high,
            "over_estimation_rate": over / len(group) if group else float("nan"),
            "mean_frequency_mae_hz_if_correct_k": float(np.mean(correct_errors)) if correct_errors else float("nan"),
        })
    return summary


def _summarize_weak(rows: list[dict]) -> list[dict]:
    summary = []
    for distance in DISTANCES_HZ:
        group = [row for row in rows if abs(float(row["weak_to_nearest_strong_distance_hz"]) - distance) < 1e-9]
        weak = _rate_row(f"weak component detected at distance {distance:g} Hz", group, lambda row: str(row["weak_detected"]).lower() == "true")
        over = _rate_row(f"over-estimation at distance {distance:g} Hz", group, lambda row: str(row["over_estimated"]).lower() == "true")
        correct = _rate_row(f"correct K at distance {distance:g} Hz", group, lambda row: str(row["correct_order"]).lower() == "true")
        summary.append({
            "weak_to_nearest_strong_distance_hz": distance,
            "runs": len(group),
            "weak_detection_rate": weak["rate"],
            "weak_detection_ci95_low": weak["ci95_low"],
            "weak_detection_ci95_high": weak["ci95_high"],
            "correct_order_rate": correct["rate"],
            "over_estimation_rate": over["rate"],
        })
    return summary


def _write_report(path: Path, context: dict) -> None:
    null_summary = context["null_summary"][0]
    lines = [
        "# Q3 实验 C：完整 SIC+BIC 定阶校准",
        "",
        "本实验运行完整 Q3 自动分离流程：GLRT 残差扫描、SIC 逐次候选、联合频率精修、BIC 定阶。结果用于替换“仅首步 GLRT 纯噪声误报率”的不完整表述。",
        "",
        "## 参数",
        "",
        f"- 样本数 N={context['sample_count']}，采样率 fs={context['fs_hz']} Hz。",
        f"- 噪声标准差 sigma={context['noise_std']}。",
        f"- 总目标误报率 0.05，最大分量数 {context['max_components']}，单轮 GLRT p_fa={context['single_step_p_fa']:.6g}。",
        f"- GLRT 阈值 Monte Carlo 次数 {context['glrt_mc']}，BIC 接受阈值 ΔBIC={context['bic_delta']}。",
        f"- 随机种子基准 SEED={SEED}。",
        "",
        "## 子实验 1：纯噪声最终误报",
        "",
        "| 条件 | 重复次数 | P(K_hat>=1) | 95% CI |",
        "|---|---:|---:|---:|",
        f"| K=0 纯噪声 | {null_summary['runs']} | {null_summary['rate']:.3%} | [{null_summary['ci95_low']:.3%}, {null_summary['ci95_high']:.3%}] |",
        "",
        "## 子实验 2：已知 K 定阶准确性",
        "",
        "| 真实 K | 重复次数 | 欠估率 | 正确率 | 95% CI | 过估率 | 条件频率 MAE/Hz |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in context["order_summary"]:
        mae = row["mean_frequency_mae_hz_if_correct_k"]
        mae_text = f"{mae:.6g}" if math.isfinite(mae) else "-"
        lines.append(
            f"| {row['true_k']} | {row['runs']} | {row['under_estimation_rate']:.3%} | "
            f"{row['correct_order_rate']:.3%} | [{row['correct_ci95_low']:.3%}, {row['correct_ci95_high']:.3%}] | "
            f"{row['over_estimation_rate']:.3%} | {mae_text} |"
        )
    lines += [
        "",
        "## 子实验 3：弱强分量混合",
        "",
        "| 弱分量到最近强分量间距/Hz | 重复次数 | 弱分量检测率 | 95% CI | 正确定阶率 | 强分量伪峰/过估率 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in context["weak_summary"]:
        lines.append(
            f"| {row['weak_to_nearest_strong_distance_hz']:.3g} | {row['runs']} | {row['weak_detection_rate']:.3%} | "
            f"[{row['weak_detection_ci95_low']:.3%}, {row['weak_detection_ci95_high']:.3%}] | "
            f"{row['correct_order_rate']:.3%} | {row['over_estimation_rate']:.3%} |"
        )
    lines += [
        "",
        "## 结论口径",
        "",
        "论文中应将 Q3 的纯噪声误报表述为完整流程最终定阶误报率，即 `P(K_hat>=1)`，而不是首步 GLRT 峰值越阈率。若引用首步 GLRT 结果，必须明确它只描述第一轮扫描。",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Q3 Experiment C full SIC+BIC order calibration.")
    parser.add_argument("--output-dir", type=Path, default=Path("q3_experiment_results/c"))
    parser.add_argument("--profile", choices=("smoke", "official"), default="official")
    parser.add_argument("--sample-count", type=int, default=40001)
    parser.add_argument("--fs", type=float, default=100.0)
    parser.add_argument("--noise-std", type=float, default=0.1)
    parser.add_argument("--null-runs", type=int, default=None)
    parser.add_argument("--order-runs", type=int, default=None)
    parser.add_argument("--weak-runs", type=int, default=None)
    parser.add_argument("--glrt-mc", type=int, default=500)
    parser.add_argument("--max-components", type=int, default=10)
    parser.add_argument("--bic-delta", type=float, default=10.0)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    return parser.parse_args()


def main() -> None:
    global _WORKER_T, _WORKER_FS, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA, _WORKER_NOISE_STD
    args = parse_args()
    defaults = {
        "smoke": {"null_runs": 20, "order_runs": 5, "weak_runs": 5},
        "official": {"null_runs": 1000, "order_runs": 500, "weak_runs": 200},
    }[args.profile]
    null_runs = args.null_runs if args.null_runs is not None else defaults["null_runs"]
    order_runs = args.order_runs if args.order_runs is not None else defaults["order_runs"]
    weak_runs = args.weak_runs if args.weak_runs is not None else defaults["weak_runs"]
    if min(null_runs, order_runs, weak_runs, args.sample_count, args.glrt_mc, args.max_components) < 1:
        raise ValueError("run counts, sample count, glrt-mc, and max-components must be positive")
    workers = max(1, args.workers)
    output_dir = args.output_dir.resolve()
    paper_dir = output_dir / "paper"
    raw_dir = output_dir / "raw"
    paper_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    t = np.arange(args.sample_count, dtype=float) / args.fs
    cfg = GLRTConfig(
        f_min=0.05,
        f_max=min(49.5, args.fs / 2.0 - 0.5),
        p_fa=0.05 / args.max_components,
        glrt_mc=args.glrt_mc,
        random_seed=SEED,
    )
    threshold = q1_compatible_glrt_threshold(args.sample_count, args.fs, cfg)
    cfg = replace(cfg, threshold=threshold)
    _WORKER_T = t
    _WORKER_FS = args.fs
    _WORKER_CFG = cfg
    _WORKER_MAX_COMPONENTS = args.max_components
    _WORKER_BIC_DELTA = args.bic_delta
    _WORKER_NOISE_STD = args.noise_std

    null_path = raw_dir / "q3_experiment_c_null_trials.csv"
    order_path = raw_dir / "q3_experiment_c_order_trials.csv"
    weak_path = raw_dir / "q3_experiment_c_weak_strong_trials.csv"

    null_rows = _run_stage("实验C-纯噪声完整流程", list(range(null_runs)), _null_worker, workers, null_path, lambda row: int(row["replicate"]))
    order_tasks = [(k, rep) for k in ORDER_K_VALUES for rep in range(order_runs)]
    order_rows = _run_stage("实验C-K定阶", order_tasks, _order_worker, workers, order_path, lambda row: (int(row["true_k"]), int(row["replicate"])))
    weak_tasks = [(distance, rep) for distance in DISTANCES_HZ for rep in range(weak_runs)]
    weak_rows = _run_stage("实验C-弱强混合", weak_tasks, _weak_strong_worker, workers, weak_path, lambda row: (float(row["weak_to_nearest_strong_distance_hz"]), int(row["replicate"])))

    null_summary = _summarize_null(null_rows)
    order_summary = _summarize_order(order_rows)
    weak_summary = _summarize_weak(weak_rows)
    _write_csv(paper_dir / "q3_experiment_c_null_false_alarm.csv", null_summary)
    _write_csv(paper_dir / "q3_experiment_c_order_accuracy.csv", order_summary)
    _write_csv(paper_dir / "q3_experiment_c_weak_strong.csv", weak_summary)
    context = {
        "profile": args.profile,
        "sample_count": args.sample_count,
        "fs_hz": args.fs,
        "noise_std": args.noise_std,
        "max_components": args.max_components,
        "single_step_p_fa": cfg.p_fa,
        "glrt_mc": args.glrt_mc,
        "glrt_threshold": threshold,
        "bic_delta": args.bic_delta,
        "workers": workers,
        "seed": SEED,
        "null_runs": null_runs,
        "order_runs_per_k": order_runs,
        "weak_runs_per_distance": weak_runs,
        "runtime_seconds": time.perf_counter() - started,
        "null_summary": null_summary,
        "order_summary": order_summary,
        "weak_summary": weak_summary,
        "command": sys.argv,
    }
    _write_report(paper_dir / "q3_experiment_c_report.md", context)
    (raw_dir / "q3_experiment_c_runtime.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "README.md").write_text(
        "\n".join([
            "# Q3 Experiment C Results",
            "",
            "This directory contains the complete SIC+BIC order-calibration experiment for Q3 issue #46.",
            "",
            "- `paper/`: paper-facing report and summary CSV tables.",
            "- `raw/`: Monte Carlo trial rows, runtime metadata, and command parameters.",
            "",
            f"Profile: `{args.profile}`.",
            "The experiment measures final model order after the full Q3 pipeline, not only the first GLRT scan.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"Experiment C complete: {output_dir}")


if __name__ == "__main__":
    main()
