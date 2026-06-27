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
from .adaptive_cupy import (
    audit_mismatch,
    build_policy_rows,
    group_id,
    parse_frequency_text,
    row_task_key,
    select_audit_tasks,
    select_pilot_tasks,
    task_cell,
)
from .core import GLRTConfig, close_pair_resolver, detect_multitone, q1_compatible_glrt_threshold
from .cupy_batch import (
    CupyBatchConfig,
    CupyFullAutoConfig,
    candidate_pairs,
    cupy_environment,
    estimate_two_tone_batch,
    estimate_two_tone_full_auto_batch,
    pair_condition_table,
)
from .experiments import wilson_interval
from q2_harmonic_recovery.outputs import line_svg
from q3_multisource_separation.outputs import convert_q3_svg_plots_to_png


SNR_LEVELS_DB = (-6.0, -12.0, -18.0)
AMPLITUDE_RATIOS = (1, 3, 10)
SEPARATIONS_HZ = (0.001, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.008, 0.010, 0.015, 0.020)
PHASE_BINS = 8
SUCCESS_EPS_HZ = 1e-7

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
_WORKER_FIT_BACKEND = None
_WORKER_TIMING_DETAIL = None


def _parse_float_list(text: str | None, default: tuple[float, ...]) -> tuple[float, ...]:
    if text is None or not text.strip():
        return default
    return tuple(float(item.strip()) for item in text.split(",") if item.strip())


def _parse_ratio_list(text: str | None, default: tuple[int, ...]) -> tuple[int, ...]:
    if text is None or not text.strip():
        return default
    values = []
    for item in text.split(","):
        token = item.strip()
        if not token:
            continue
        values.append(int(token.split(":")[-1]))
    return tuple(values)


def _rng(experiment_id: int, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, 47, experiment_id, replicate]))


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    for row in rows[1:]:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
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


def _init_worker(t, fs, center_hz, weak_amplitude, grid_step_hz, conditional_threshold, detector, cfg, max_components, bic_delta, fit_backend, timing_detail) -> None:
    global _WORKER_T, _WORKER_FS, _WORKER_CENTER_HZ, _WORKER_WEAK_AMPLITUDE, _WORKER_GRID_STEP_HZ
    global _WORKER_CONDITIONAL_THRESHOLD, _WORKER_DETECTOR, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA
    global _WORKER_FIT_BACKEND, _WORKER_TIMING_DETAIL
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
    _WORKER_FIT_BACKEND = fit_backend
    _WORKER_TIMING_DETAIL = timing_detail


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
    trial_started = time.perf_counter()
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
    signal_elapsed = time.perf_counter() - trial_started

    detector_started = time.perf_counter()
    if _WORKER_DETECTOR == "complete":
        fit, history = detect_multitone(
            _WORKER_T,
            observed,
            _WORKER_FS,
            _WORKER_CFG,
            max_components=_WORKER_MAX_COMPONENTS,
            bic_delta=_WORKER_BIC_DELTA,
            fit_backend=_WORKER_FIT_BACKEND,
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
    detector_elapsed = time.perf_counter() - detector_started
    estimated = np.asarray(fit["frequencies_hz"], float)
    tolerance = separation_hz / 4.0
    max_error = _match_max_error(estimated, frequencies)
    success = bool(
        estimated_k == 2
        and math.isfinite(max_error)
        and max_error <= tolerance + SUCCESS_EPS_HZ
        and not fit["ill_conditioned"]
    )
    phase_diff = _phase_difference(phases)
    phase_bin = min(PHASE_BINS - 1, int(phase_diff / math.pi * PHASE_BINS))
    row = {
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
        "runtime_seconds": detector_elapsed,
    }
    if _WORKER_TIMING_DETAIL:
        row.update({
            "signal_generation_runtime_seconds": signal_elapsed,
            "detector_runtime_seconds": detector_elapsed,
            "trial_total_runtime_seconds": time.perf_counter() - trial_started,
            "fit_backend": _WORKER_FIT_BACKEND,
        })
    return row


def _build_trial_observation(task: tuple[float, int, float, int]) -> dict:
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
    return {
        "task": task,
        "observed": observed,
        "frequencies": frequencies,
        "amplitudes": amplitudes,
        "phases": phases,
        "noise_std": noise_std,
    }


def _row_from_cupy_estimate(
    payload: dict,
    estimate: dict,
    backend_label: str,
    signal_elapsed: float,
    detector_elapsed: float,
    adaptive: dict | None = None,
) -> dict:
    snr_db, amplitude_ratio, separation_hz, replicate = payload["task"]
    frequencies = payload["frequencies"]
    phases = payload["phases"]
    estimated = np.asarray(estimate["estimated_frequencies_hz"], float)
    estimated_k = int(estimate["estimated_k"])
    tolerance = separation_hz / 4.0
    max_error = _match_max_error(estimated, frequencies)
    success = bool(
        estimated_k == 2
        and math.isfinite(max_error)
        and max_error <= tolerance + SUCCESS_EPS_HZ
        and not estimate["ill_conditioned"]
    )
    phase_diff = _phase_difference(phases)
    phase_bin = min(PHASE_BINS - 1, int(phase_diff / math.pi * PHASE_BINS))
    adaptive = adaptive or {}
    return {
        "snr_weak_db": snr_db,
        "amplitude_ratio_weak_to_strong": f"1:{amplitude_ratio}",
        "amplitude_ratio_value": amplitude_ratio,
        "separation_hz": separation_hz,
        "replicate": replicate,
        "center_hz": _WORKER_CENTER_HZ,
        "true_frequency_1_hz": frequencies[0],
        "true_frequency_2_hz": frequencies[1],
        "weak_amplitude": payload["amplitudes"][0],
        "strong_amplitude": payload["amplitudes"][1],
        "noise_std": payload["noise_std"],
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
        "bic_improvement": estimate["bic_improvement"],
        "candidate_origin": adaptive.get("candidate_origin", estimate["candidate_origin"]),
        "conditional_glrt_statistic": float("nan"),
        "conditional_glrt_threshold": float("nan"),
        "condition_design": estimate["condition_design"],
        "ill_conditioned": bool(estimate["ill_conditioned"]),
        "runtime_seconds": detector_elapsed,
        "signal_generation_runtime_seconds": signal_elapsed,
        "detector_runtime_seconds": detector_elapsed,
        "trial_total_runtime_seconds": signal_elapsed + detector_elapsed,
        "fit_backend": backend_label,
        "cupy_best_pair_index": estimate["cupy_best_pair_index"],
        "cupy_best_pair_bic": estimate["cupy_best_pair_bic"],
        "cupy_best_single_bic": estimate["cupy_best_single_bic"],
        "cupy_coarse_center_hz": estimate.get("cupy_coarse_center_hz", float("nan")),
        "adaptive_group_id": adaptive.get("adaptive_group_id", ""),
        "adaptive_phase": adaptive.get("adaptive_phase", ""),
        "adaptive_policy_center_hz": adaptive.get("adaptive_policy_center_hz", float("nan")),
        "adaptive_policy_span_hz": adaptive.get("adaptive_policy_span_hz", float("nan")),
        "adaptive_policy_source": adaptive.get("adaptive_policy_source", ""),
    }


def _adaptive_row_needs_fallback(
    row: dict,
    boundary_ratio: float,
    separation_min_hz: float,
    separation_max_hz: float,
    separation_step_hz: float,
) -> tuple[bool, str]:
    reasons = []
    if int(float(row["estimated_k"])) != 2:
        reasons.append("estimated_k")
    if str(row["ill_conditioned"]).lower() == "true":
        reasons.append("ill_conditioned")
    span = float(row.get("adaptive_policy_span_hz", float("nan")))
    center = float(row.get("adaptive_policy_center_hz", float("nan")))
    estimated = parse_frequency_text(str(row.get("estimated_frequencies_hz", "")))
    if len(estimated) >= 2 and math.isfinite(span) and span > 0 and math.isfinite(center):
        sorted_estimated = np.sort(estimated)[:2]
        estimated_center = float(np.mean(sorted_estimated))
        if abs(estimated_center - center) >= boundary_ratio * span:
            reasons.append("center_boundary")
        estimated_separation = float(abs(sorted_estimated[1] - sorted_estimated[0]))
        separation_edge_tol = max(float(separation_step_hz) * 0.5, 1e-12)
        if math.isfinite(separation_min_hz) and estimated_separation <= separation_min_hz + separation_edge_tol:
            reasons.append("separation_min_boundary")
        if math.isfinite(separation_max_hz) and estimated_separation >= separation_max_hz - separation_edge_tol:
            reasons.append("separation_max_boundary")
    return bool(reasons), ";".join(reasons)


def _run_stage(tasks: list[tuple[float, int, float, int]], worker: Callable, workers: int, path: Path, chunksize: int) -> list[dict]:
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
                _WORKER_FIT_BACKEND,
                _WORKER_TIMING_DETAIL,
            ),
        ) as pool:
            for count, row in enumerate(pool.map(worker, pending, chunksize=max(1, chunksize)), 1):
                record(row, count)
    return existing_rows + new_rows


def _run_cupy_stage(
    tasks: list[tuple[float, int, float, int]],
    path: Path,
    batch_size: int,
    config: CupyBatchConfig | CupyFullAutoConfig,
    backend_label: str,
) -> tuple[list[dict], dict]:
    existing_rows = _read_csv(path)
    existing = {
        (float(row["snr_weak_db"]), int(float(row["amplitude_ratio_value"])), float(row["separation_hz"]), int(row["replicate"]))
        for row in existing_rows
    }
    pending = [task for task in tasks if task not in existing]
    env = cupy_environment()
    if not pending:
        return existing_rows, {"cupy_environment": env, "cupy_batches": []}

    pairs = None
    conditions = None
    if backend_label == "cupy_batch":
        pairs = candidate_pairs(config)
        conditions = pair_condition_table(_WORKER_T, pairs)
    started = time.perf_counter()
    new_rows: list[dict] = []
    buffer: list[dict] = []
    batch_records: list[dict] = []

    for offset in range(0, len(pending), batch_size):
        batch_tasks = pending[offset:offset + batch_size]
        signal_started = time.perf_counter()
        payloads = [_build_trial_observation(task) for task in batch_tasks]
        observations = np.stack([item["observed"] for item in payloads], axis=0)
        signal_elapsed = time.perf_counter() - signal_started

        if backend_label == "cupy_full_auto":
            estimates, timing = estimate_two_tone_full_auto_batch(_WORKER_T, observations, config)
        else:
            estimates, timing = estimate_two_tone_batch(_WORKER_T, observations, config, pairs=pairs, conditions=conditions)
        detector_elapsed = float(timing["cupy_total_seconds"])
        per_row_detector = detector_elapsed / max(len(payloads), 1)
        per_row_signal = signal_elapsed / max(len(payloads), 1)

        for payload, estimate in zip(payloads, estimates):
            row = _row_from_cupy_estimate(
                payload,
                estimate,
                backend_label,
                per_row_signal,
                per_row_detector,
            )
            new_rows.append(row)
            buffer.append(row)
        timing_record = {
            **timing,
            "signal_generation_seconds": signal_elapsed,
            "batch_start_index": offset,
            "batch_rows": len(payloads),
        }
        batch_records.append(timing_record)
        if len(buffer) >= 25 or offset + batch_size >= len(pending):
            _append_csv(path, buffer)
            buffer.clear()
        count = min(offset + batch_size, len(pending))
        elapsed = time.perf_counter() - started
        rate = elapsed / max(count, 1)
        remain = rate * (len(pending) - count)
        print(f"实验D-CuPy批处理: {count}/{len(pending)}; elapsed={elapsed:.1f}s; remaining≈{remain:.1f}s", flush=True)
    return existing_rows + new_rows, {"cupy_environment": env, "cupy_batches": batch_records}


def _run_cupy_adaptive_stage(
    tasks: list[tuple[float, int, float, int]],
    trial_path: Path,
    raw_dir: Path,
    batch_size: int,
    full_auto_config: CupyFullAutoConfig,
    pilot_runs_per_cell: int,
    audit_rate: float,
    min_center_span_hz: float,
    center_margin_hz: float,
    max_center_span_hz: float,
    audit_frequency_tolerance_hz: float,
    enable_fallback: bool,
    fallback_boundary_ratio: float,
    policy_center_offset_hz: float,
    fast_center_step_hz: float,
    separation_min_hz: float,
    separation_max_hz: float,
    separation_step_hz: float,
) -> tuple[list[dict], dict]:
    if trial_path.exists() and trial_path.stat().st_size > 0:
        return _read_csv(trial_path), {
            "cupy_environment": cupy_environment(),
            "adaptive_existing_trials_reused": True,
            "adaptive_uses_true_center": False,
        }

    env = cupy_environment()
    started = time.perf_counter()
    pilot_tasks = sorted(select_pilot_tasks(tasks, pilot_runs_per_cell))
    fast_tasks = [task for task in tasks if task not in set(pilot_tasks)]
    batch_records: list[dict] = []

    def run_full_auto(task_list: list[tuple[float, int, float, int]], phase: str) -> list[dict]:
        rows: list[dict] = []
        for offset in range(0, len(task_list), batch_size):
            batch_tasks = task_list[offset:offset + batch_size]
            signal_started = time.perf_counter()
            payloads = [_build_trial_observation(task) for task in batch_tasks]
            observations = np.stack([item["observed"] for item in payloads], axis=0)
            signal_elapsed = time.perf_counter() - signal_started
            estimates, timing = estimate_two_tone_full_auto_batch(_WORKER_T, observations, full_auto_config)
            detector_elapsed = float(timing["cupy_total_seconds"])
            for payload, estimate in zip(payloads, estimates):
                cell = task_cell(payload["task"])
                rows.append(
                    _row_from_cupy_estimate(
                        payload,
                        estimate,
                        "cupy_adaptive",
                        signal_elapsed / max(len(payloads), 1),
                        detector_elapsed / max(len(payloads), 1),
                        {
                            "candidate_origin": f"adaptive_{phase}_full_auto",
                            "adaptive_group_id": group_id(cell),
                            "adaptive_phase": phase,
                            "adaptive_policy_center_hz": float("nan"),
                            "adaptive_policy_span_hz": float("nan"),
                            "adaptive_policy_source": "full_auto",
                        },
                    )
                )
            batch_records.append({
                **timing,
                "adaptive_phase": phase,
                "signal_generation_seconds": signal_elapsed,
                "batch_start_index": offset,
                "batch_rows": len(payloads),
            })
            count = min(offset + batch_size, len(task_list))
            print(f"实验D-CuPy自适应{phase}: {count}/{len(task_list)}", flush=True)
        return rows

    pilot_started = time.perf_counter()
    pilot_rows = run_full_auto(pilot_tasks, "pilot")
    pilot_elapsed = time.perf_counter() - pilot_started
    policy_rows, policies = build_policy_rows(
        pilot_rows,
        min_span_hz=min_center_span_hz,
        margin_hz=center_margin_hz,
        max_span_hz=max_center_span_hz,
    )
    _write_csv(raw_dir / "q3_experiment_d_adaptive_policy.csv", policy_rows)
    (raw_dir / "q3_experiment_d_adaptive_policy.json").write_text(
        json.dumps(policy_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv(raw_dir / "q3_experiment_d_adaptive_pilot_trials.csv", pilot_rows)
    if abs(policy_center_offset_hz) > 0:
        shifted_policy_rows = []
        for row in policy_rows:
            shifted = dict(row)
            shifted["adaptive_policy_center_hz_unshifted"] = row["adaptive_policy_center_hz"]
            shifted["adaptive_policy_center_hz"] = float(row["adaptive_policy_center_hz"]) + policy_center_offset_hz
            shifted["adaptive_policy_center_offset_hz"] = policy_center_offset_hz
            shifted["adaptive_policy_source"] = f"{row['adaptive_policy_source']}_stress_offset"
            shifted_policy_rows.append(shifted)
        policy_rows = shifted_policy_rows
        for cell, policy in list(policies.items()):
            policies[cell] = replace(
                policy,
                center_hz=policy.center_hz + policy_center_offset_hz,
                source=f"{policy.source}_stress_offset",
            )
        _write_csv(raw_dir / "q3_experiment_d_adaptive_policy_stress_shifted.csv", policy_rows)
        _write_csv(raw_dir / "q3_experiment_d_adaptive_policy.csv", policy_rows)
        (raw_dir / "q3_experiment_d_adaptive_policy.json").write_text(
            json.dumps(policy_rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    fast_started = time.perf_counter()
    fast_rows: list[dict] = []
    fast_groups: dict[tuple[float, int, float], list[tuple[float, int, float, int]]] = {}
    for task in fast_tasks:
        fast_groups.setdefault(task_cell(task), []).append(task)
    for cell, cell_tasks in sorted(fast_groups.items()):
        policy = policies[cell]
        fast_config = CupyBatchConfig(
            center_hz=policy.center_hz,
            fs=_WORKER_FS,
            bic_delta=_WORKER_BIC_DELTA,
            center_span_hz=policy.center_span_hz,
            center_step_hz=fast_center_step_hz,
            separation_min_hz=separation_min_hz,
            separation_max_hz=separation_max_hz,
            separation_step_hz=separation_step_hz,
        )
        pairs = candidate_pairs(fast_config)
        conditions = pair_condition_table(_WORKER_T, pairs)
        for offset in range(0, len(cell_tasks), batch_size):
            batch_tasks = cell_tasks[offset:offset + batch_size]
            signal_started = time.perf_counter()
            payloads = [_build_trial_observation(task) for task in batch_tasks]
            observations = np.stack([item["observed"] for item in payloads], axis=0)
            signal_elapsed = time.perf_counter() - signal_started
            estimates, timing = estimate_two_tone_batch(_WORKER_T, observations, fast_config, pairs=pairs, conditions=conditions)
            detector_elapsed = float(timing["cupy_total_seconds"])
            for payload, estimate in zip(payloads, estimates):
                fast_rows.append(
                    _row_from_cupy_estimate(
                        payload,
                        estimate,
                        "cupy_adaptive",
                        signal_elapsed / max(len(payloads), 1),
                        detector_elapsed / max(len(payloads), 1),
                        {
                            "candidate_origin": "adaptive_fast_learned_center",
                            "adaptive_group_id": policy.group_id,
                            "adaptive_phase": "fast",
                            "adaptive_policy_center_hz": policy.center_hz,
                            "adaptive_policy_span_hz": policy.center_span_hz,
                            "adaptive_policy_source": policy.source,
                        },
                    )
                )
            batch_records.append({
                **timing,
                "adaptive_phase": "fast",
                "adaptive_group_id": policy.group_id,
                "signal_generation_seconds": signal_elapsed,
                "batch_start_index": offset,
                "batch_rows": len(payloads),
            })
        print(f"实验D-CuPy自适应fast: {policy.group_id}; rows={len(cell_tasks)}", flush=True)
    fast_elapsed = time.perf_counter() - fast_started

    fallback_started = time.perf_counter()
    fallback_events = []
    fallback_rows: list[dict] = []
    if enable_fallback:
        fallback_tasks = []
        fallback_reasons = {}
        for row in fast_rows:
            needs_fallback, reason = _adaptive_row_needs_fallback(
                row,
                fallback_boundary_ratio,
                separation_min_hz,
                separation_max_hz,
                separation_step_hz,
            )
            if needs_fallback:
                task = row_task_key(row)
                fallback_tasks.append(task)
                fallback_reasons[task] = reason
        fallback_tasks = sorted(set(fallback_tasks))
        fallback_rows = run_full_auto(fallback_tasks, "fallback") if fallback_tasks else []
        fallback_by_task = {row_task_key(row): row for row in fallback_rows}
        fast_by_task_initial = {row_task_key(row): row for row in fast_rows}
        final_fast_rows = []
        for row in fast_rows:
            task = row_task_key(row)
            fallback_row = fallback_by_task.get(task)
            if fallback_row is None:
                final_fast_rows.append(row)
                continue
            policy = policies[task_cell(task)]
            fallback_row["adaptive_group_id"] = policy.group_id
            fallback_row["adaptive_phase"] = "fallback"
            fallback_row["adaptive_policy_center_hz"] = policy.center_hz
            fallback_row["adaptive_policy_span_hz"] = policy.center_span_hz
            fallback_row["adaptive_policy_source"] = policy.source
            fallback_row["candidate_origin"] = "adaptive_fallback_full_auto"
            final_fast_rows.append(fallback_row)
            fast_row = fast_by_task_initial[task]
            mismatched, reason, frequency_delta = audit_mismatch(fast_row, fallback_row, audit_frequency_tolerance_hz)
            fallback_events.append({
                "snr_weak_db": task[0],
                "amplitude_ratio_value": task[1],
                "separation_hz": task[2],
                "replicate": task[3],
                "adaptive_group_id": policy.group_id,
                "fallback_reason": fallback_reasons.get(task, ""),
                "changed_result": mismatched,
                "change_reason": reason,
                "frequency_delta_hz": frequency_delta,
                "fast_success": fast_row["success"],
                "fallback_success": fallback_row["success"],
                "fast_estimated_k": fast_row["estimated_k"],
                "fallback_estimated_k": fallback_row["estimated_k"],
                "fast_estimated_frequencies_hz": fast_row["estimated_frequencies_hz"],
                "fallback_estimated_frequencies_hz": fallback_row["estimated_frequencies_hz"],
            })
        fast_rows = final_fast_rows
    fallback_elapsed = time.perf_counter() - fallback_started
    _write_csv(raw_dir / "q3_experiment_d_adaptive_fallback_events.csv", fallback_events)

    audit_started = time.perf_counter()
    audit_tasks = sorted(select_audit_tasks(fast_tasks, audit_rate))
    audit_rows = run_full_auto(audit_tasks, "audit") if audit_tasks else []
    audit_elapsed = time.perf_counter() - audit_started
    _write_csv(raw_dir / "q3_experiment_d_adaptive_audit_trials.csv", audit_rows)
    fast_by_task = {row_task_key(row): row for row in fast_rows}
    discrepancies = []
    for audit_row in audit_rows:
        key = row_task_key(audit_row)
        fast_row = fast_by_task.get(key)
        if fast_row is None:
            continue
        mismatched, reason, frequency_delta = audit_mismatch(fast_row, audit_row, audit_frequency_tolerance_hz)
        discrepancies.append({
            "snr_weak_db": key[0],
            "amplitude_ratio_value": key[1],
            "separation_hz": key[2],
            "replicate": key[3],
            "adaptive_group_id": fast_row["adaptive_group_id"],
            "mismatch": mismatched,
            "mismatch_reason": reason,
            "frequency_delta_hz": frequency_delta,
            "fast_success": fast_row["success"],
            "audit_success": audit_row["success"],
            "fast_estimated_k": fast_row["estimated_k"],
            "audit_estimated_k": audit_row["estimated_k"],
            "fast_estimated_frequencies_hz": fast_row["estimated_frequencies_hz"],
            "audit_estimated_frequencies_hz": audit_row["estimated_frequencies_hz"],
        })
    _write_csv(raw_dir / "q3_experiment_d_adaptive_audit_discrepancies.csv", discrepancies)

    all_rows = sorted(pilot_rows + fast_rows, key=lambda row: row_task_key(row))
    _write_csv(trial_path, all_rows)
    _write_csv(raw_dir / "q3_experiment_d_adaptive_timing.csv", batch_records)
    mismatch_count = sum(1 for row in discrepancies if row["mismatch"])
    adaptive_run = {
        "cupy_environment": env,
        "adaptive_uses_true_center": False,
        "adaptive_pilot_runs_per_cell": pilot_runs_per_cell,
        "adaptive_audit_rate": audit_rate,
        "adaptive_audit_frequency_tolerance_hz": audit_frequency_tolerance_hz,
        "adaptive_policy_center_offset_hz": policy_center_offset_hz,
        "adaptive_pilot_rows": len(pilot_rows),
        "adaptive_fast_rows": len(fast_rows),
        "adaptive_fallback_rows": len(fallback_rows),
        "adaptive_fallback_events": len(fallback_events),
        "adaptive_fallback_changed_results": sum(1 for row in fallback_events if row["changed_result"]),
        "adaptive_audit_rows": len(audit_rows),
        "adaptive_audit_mismatches": mismatch_count,
        "adaptive_audit_mismatch_rate": mismatch_count / len(discrepancies) if discrepancies else float("nan"),
        "adaptive_policy_count": len(policy_rows),
        "adaptive_pilot_seconds": pilot_elapsed,
        "adaptive_fast_seconds": fast_elapsed,
        "adaptive_fallback_seconds": fallback_elapsed,
        "adaptive_audit_seconds": audit_elapsed,
        "adaptive_total_seconds": time.perf_counter() - started,
        "cupy_batches": batch_records,
    }
    return all_rows, adaptive_run


def _summarize_surface(rows: list[dict], snr_levels: tuple[float, ...], amplitude_ratios: tuple[int, ...], separations: tuple[float, ...]) -> list[dict]:
    summary = []
    for snr_db in snr_levels:
        for ratio in amplitude_ratios:
            for separation in separations:
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


def _summarize_phase(rows: list[dict], snr_levels: tuple[float, ...], amplitude_ratios: tuple[int, ...], separations: tuple[float, ...]) -> list[dict]:
    summary = []
    for snr_db in snr_levels:
        for ratio in amplitude_ratios:
            for separation in separations:
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


def _summarize_limits(summary: list[dict], target: float, snr_levels: tuple[float, ...], amplitude_ratios: tuple[int, ...]) -> list[dict]:
    rows = []
    for snr_db in snr_levels:
        for ratio in amplitude_ratios:
            rows.append({
                "snr_weak_db": snr_db,
                "amplitude_ratio_weak_to_strong": f"1:{ratio}",
                "amplitude_ratio_value": ratio,
                "success_standard": target,
                "empirical_resolution_limit_hz": _empirical_limit(summary, snr_db, ratio, target),
            })
    return rows


def _mean_float(rows: list[dict], key: str) -> float:
    values = [float(row[key]) for row in rows if key in row and row[key] not in ("", None)]
    return float(np.mean(values)) if values else float("nan")


def _summarize_timing(rows: list[dict], snr_levels: tuple[float, ...], amplitude_ratios: tuple[int, ...], separations: tuple[float, ...]) -> list[dict]:
    summary = []
    has_detail = any("trial_total_runtime_seconds" in row for row in rows)
    for snr_db in snr_levels:
        for ratio in amplitude_ratios:
            for separation in separations:
                group = [
                    row for row in rows
                    if float(row["snr_weak_db"]) == snr_db
                    and int(float(row["amplitude_ratio_value"])) == ratio
                    and abs(float(row["separation_hz"]) - separation) < 1e-12
                ]
                if not group:
                    continue
                summary.append({
                    "snr_weak_db": snr_db,
                    "amplitude_ratio_weak_to_strong": f"1:{ratio}",
                    "amplitude_ratio_value": ratio,
                    "separation_hz": separation,
                    "runs": len(group),
                    "mean_runtime_seconds": _mean_float(group, "runtime_seconds"),
                    "mean_signal_generation_runtime_seconds": _mean_float(group, "signal_generation_runtime_seconds") if has_detail else float("nan"),
                    "mean_detector_runtime_seconds": _mean_float(group, "detector_runtime_seconds") if has_detail else float("nan"),
                    "mean_trial_total_runtime_seconds": _mean_float(group, "trial_total_runtime_seconds") if has_detail else float("nan"),
                    "max_trial_total_runtime_seconds": max((float(row["trial_total_runtime_seconds"]) for row in group if "trial_total_runtime_seconds" in row), default=float("nan")),
                })
    return summary


def _write_plots(
    paper_dir: Path,
    surface: list[dict],
    phase: list[dict],
    snr_levels: tuple[float, ...],
    amplitude_ratios: tuple[int, ...],
) -> list[Path]:
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
    fallback_colors = ["#1f77b4", "#2ca02c", "#17becf", "#ff7f0e", "#9467bd", "#bcbd22", "#d62728", "#8c564b", "#7f7f7f"]
    color_index = 0
    for snr_db in snr_levels:
        for ratio in amplitude_ratios:
            rows = [
                row for row in surface
                if float(row["snr_weak_db"]) == snr_db and int(float(row["amplitude_ratio_value"])) == ratio
            ]
            rows.sort(key=lambda row: float(row["separation_hz"]))
            if not rows:
                continue
            color = colors.get((snr_db, ratio), fallback_colors[color_index % len(fallback_colors)])
            color_index += 1
            series.append((
                f"SNR {snr_db:g} dB，幅比1:{ratio}",
                [float(row["separation_hz"]) for row in rows],
                [float(row["success_rate"]) for row in rows],
                color,
            ))
    line_svg(
        paper_dir / "q3_experiment_d_success_surface.svg",
        "Q3 条件化近频辨识成功率",
        "频率间隔 Δf (Hz)",
        "成功率",
        series,
    )

    phase_series = []
    for snr_db, ratio in list(zip(snr_levels, amplitude_ratios))[:3]:
        rows = [
            row for row in phase
            if float(row["snr_weak_db"]) == snr_db and int(float(row["amplitude_ratio_value"])) == ratio
        ]
        rows.sort(key=lambda row: float(row["separation_hz"]))
        if not rows:
            continue
        color = colors.get((snr_db, ratio), fallback_colors[color_index % len(fallback_colors)])
        color_index += 1
        phase_series.append((
            f"平均 SNR {snr_db:g} dB 幅比1:{ratio}",
            [float(row["separation_hz"]) for row in rows],
            [float(row["random_phase_average_success_rate"]) for row in rows],
            color,
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
        f"- 弱分量幅值 {context['weak_amplitude']}，强分量按 {', '.join(context['amplitude_ratios'])} 放大。",
        f"- SNR 以较弱分量计：{', '.join(f'{value:g} dB' for value in context['snr_levels_db'])}。",
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
    parser.add_argument("--output-dir", type=Path, default=Path("q3_experiment_results/d"))
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
    parser.add_argument("--chunksize", type=int, default=1)
    parser.add_argument("--fit-backend", choices=("dense", "cached"), default="cached")
    parser.add_argument("--compute-backend", choices=("cpu", "cpu_cached", "cupy_batch", "cupy_full_auto", "cupy_adaptive"), default="cpu_cached")
    parser.add_argument("--cupy-batch-size", type=int, default=64)
    parser.add_argument("--cupy-center-span-hz", type=float, default=0.0)
    parser.add_argument("--cupy-center-step-hz", type=float, default=0.00025)
    parser.add_argument("--cupy-separation-min-hz", type=float, default=0.0005)
    parser.add_argument("--cupy-separation-max-hz", type=float, default=0.022)
    parser.add_argument("--cupy-separation-step-hz", type=float, default=0.00025)
    parser.add_argument("--cupy-auto-f-min-hz", type=float, default=0.5)
    parser.add_argument("--cupy-auto-f-max-hz", type=float, default=20.0)
    parser.add_argument("--cupy-auto-center-span-hz", type=float, default=0.006)
    parser.add_argument("--cupy-auto-center-step-hz", type=float, default=0.00025)
    parser.add_argument("--cupy-auto-row-batch-size", type=int, default=4)
    parser.add_argument("--cupy-auto-candidate-chunk-size", type=int, default=128)
    parser.add_argument("--adaptive-pilot-runs-per-cell", type=int, default=3)
    parser.add_argument("--adaptive-audit-rate", type=float, default=0.05)
    parser.add_argument("--adaptive-min-center-span-hz", type=float, default=0.001)
    parser.add_argument("--adaptive-center-margin-hz", type=float, default=0.0005)
    parser.add_argument("--adaptive-max-center-span-hz", type=float, default=0.006)
    parser.add_argument("--adaptive-audit-frequency-tolerance-hz", type=float, default=0.0005)
    parser.add_argument("--adaptive-disable-fallback", action="store_true")
    parser.add_argument("--adaptive-fallback-boundary-ratio", type=float, default=0.9)
    parser.add_argument("--adaptive-policy-center-offset-hz", type=float, default=0.0)
    parser.add_argument("--timing-detail", action="store_true")
    parser.add_argument("--snr-levels", type=str, default=None)
    parser.add_argument("--amplitude-ratios", type=str, default=None)
    parser.add_argument("--separations", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    global _WORKER_T, _WORKER_FS, _WORKER_CENTER_HZ, _WORKER_WEAK_AMPLITUDE, _WORKER_GRID_STEP_HZ
    global _WORKER_CONDITIONAL_THRESHOLD, _WORKER_DETECTOR, _WORKER_CFG, _WORKER_MAX_COMPONENTS, _WORKER_BIC_DELTA
    global _WORKER_FIT_BACKEND, _WORKER_TIMING_DETAIL
    args = parse_args()
    default_runs = {"smoke": 3, "official": 200}[args.profile]
    runs = args.runs if args.runs is not None else default_runs
    if min(args.sample_count, runs, args.workers) < 1:
        raise ValueError("sample-count, runs, and workers must be positive")
    if args.chunksize < 1:
        raise ValueError("chunksize must be positive")
    if args.cupy_batch_size < 1:
        raise ValueError("cupy-batch-size must be positive")
    if args.cupy_separation_min_hz <= 0 or args.cupy_separation_max_hz <= args.cupy_separation_min_hz:
        raise ValueError("cupy separation range must be positive and increasing")
    if args.cupy_separation_step_hz <= 0 or args.cupy_center_step_hz <= 0:
        raise ValueError("cupy grid steps must be positive")
    if args.cupy_auto_center_step_hz <= 0:
        raise ValueError("cupy auto center step must be positive")
    if args.cupy_auto_row_batch_size < 1 or args.cupy_auto_candidate_chunk_size < 1:
        raise ValueError("cupy auto row batch size and candidate chunk size must be positive")
    if args.cupy_auto_f_max_hz <= args.cupy_auto_f_min_hz:
        raise ValueError("cupy auto frequency range must be increasing")
    if args.adaptive_pilot_runs_per_cell < 1:
        raise ValueError("adaptive pilot runs per cell must be positive")
    if not (0.0 <= args.adaptive_audit_rate <= 1.0):
        raise ValueError("adaptive audit rate must be in [0, 1]")
    if args.adaptive_min_center_span_hz < 0 or args.adaptive_center_margin_hz < 0:
        raise ValueError("adaptive center span and margin must be non-negative")
    if args.adaptive_max_center_span_hz < args.adaptive_min_center_span_hz:
        raise ValueError("adaptive max center span must be at least min center span")
    if args.adaptive_audit_frequency_tolerance_hz < 0:
        raise ValueError("adaptive audit frequency tolerance must be non-negative")
    if not (0.0 < args.adaptive_fallback_boundary_ratio <= 1.0):
        raise ValueError("adaptive fallback boundary ratio must be in (0, 1]")
    if not math.isfinite(args.adaptive_policy_center_offset_hz):
        raise ValueError("adaptive policy center offset must be finite")
    if not (0.0 < args.target_success <= 1.0):
        raise ValueError("target-success must be in (0, 1]")
    if args.compute_backend == "cpu":
        args.fit_backend = "dense"
    elif args.compute_backend == "cpu_cached":
        args.fit_backend = "cached"
    snr_levels = _parse_float_list(args.snr_levels, SNR_LEVELS_DB)
    amplitude_ratios = _parse_ratio_list(args.amplitude_ratios, AMPLITUDE_RATIOS)
    separations = _parse_float_list(args.separations, SEPARATIONS_HZ)

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
    _WORKER_DETECTOR = args.compute_backend if args.compute_backend in ("cupy_batch", "cupy_full_auto", "cupy_adaptive") else args.detector
    _WORKER_MAX_COMPONENTS = args.max_components
    _WORKER_BIC_DELTA = args.bic_delta
    _WORKER_FIT_BACKEND = args.fit_backend
    _WORKER_TIMING_DETAIL = args.timing_detail
    cfg = GLRTConfig(
        f_min=0.05,
        f_max=min(49.5, args.fs / 2.0 - 0.5),
        p_fa=0.05 / args.max_components,
        glrt_mc=args.glrt_mc,
        random_seed=SEED,
    )
    threshold = None if args.compute_backend in ("cupy_batch", "cupy_full_auto", "cupy_adaptive") else q1_compatible_glrt_threshold(args.sample_count, args.fs, cfg)
    _WORKER_CFG = replace(cfg, threshold=threshold)

    tasks = [
        (snr_db, ratio, separation, replicate)
        for snr_db in snr_levels
        for ratio in amplitude_ratios
        for separation in separations
        for replicate in range(runs)
    ]
    trial_path = raw_dir / "q3_experiment_d_trials.csv"
    cupy_run: dict = {}
    if args.compute_backend in ("cupy_batch", "cupy_full_auto", "cupy_adaptive"):
        if args.compute_backend in ("cupy_full_auto", "cupy_adaptive"):
            cupy_config = CupyFullAutoConfig(
                fs=args.fs,
                bic_delta=args.bic_delta,
                f_min_hz=args.cupy_auto_f_min_hz,
                f_max_hz=args.cupy_auto_f_max_hz,
                local_center_span_hz=args.cupy_auto_center_span_hz,
                local_center_step_hz=args.cupy_auto_center_step_hz,
                separation_min_hz=args.cupy_separation_min_hz,
                separation_max_hz=args.cupy_separation_max_hz,
                separation_step_hz=args.cupy_separation_step_hz,
                row_batch_size=args.cupy_auto_row_batch_size,
                candidate_chunk_size=args.cupy_auto_candidate_chunk_size,
            )
        else:
            cupy_config = CupyBatchConfig(
                center_hz=args.center_hz,
                fs=args.fs,
                bic_delta=args.bic_delta,
                center_span_hz=args.cupy_center_span_hz,
                center_step_hz=args.cupy_center_step_hz,
                separation_min_hz=args.cupy_separation_min_hz,
                separation_max_hz=args.cupy_separation_max_hz,
                separation_step_hz=args.cupy_separation_step_hz,
            )
        if args.compute_backend == "cupy_adaptive":
            rows, cupy_run = _run_cupy_adaptive_stage(
                tasks,
                trial_path,
                raw_dir,
                args.cupy_batch_size,
                cupy_config,
                args.adaptive_pilot_runs_per_cell,
                args.adaptive_audit_rate,
                args.adaptive_min_center_span_hz,
                args.adaptive_center_margin_hz,
                args.adaptive_max_center_span_hz,
                args.adaptive_audit_frequency_tolerance_hz,
                not args.adaptive_disable_fallback,
                args.adaptive_fallback_boundary_ratio,
                args.adaptive_policy_center_offset_hz,
                args.cupy_center_step_hz,
                args.cupy_separation_min_hz,
                args.cupy_separation_max_hz,
                args.cupy_separation_step_hz,
            )
        else:
            rows, cupy_run = _run_cupy_stage(tasks, trial_path, args.cupy_batch_size, cupy_config, args.compute_backend)
        if cupy_run.get("cupy_batches"):
            _write_csv(raw_dir / "q3_experiment_d_cupy_batch_timing.csv", cupy_run["cupy_batches"])
    else:
        rows = _run_stage(tasks, _trial_worker, max(1, args.workers), trial_path, args.chunksize)

    surface_summary = _summarize_surface(rows, snr_levels, amplitude_ratios, separations)
    phase_summary = _summarize_phase(rows, snr_levels, amplitude_ratios, separations)
    limit_summary = _summarize_limits(surface_summary, args.target_success, snr_levels, amplitude_ratios)
    timing_summary = _summarize_timing(rows, snr_levels, amplitude_ratios, separations) if args.timing_detail else []
    _write_csv(paper_dir / "q3_experiment_d_success_surface.csv", surface_summary)
    _write_csv(paper_dir / "q3_experiment_d_resolution_limits.csv", limit_summary)
    _write_csv(paper_dir / "q3_experiment_d_phase_effect.csv", phase_summary)
    if args.timing_detail:
        _write_csv(raw_dir / "q3_experiment_d_timing_summary.csv", timing_summary)
    pngs = _write_plots(paper_dir, surface_summary, phase_summary, snr_levels, amplitude_ratios)

    context = {
        "profile": args.profile,
        "compute_backend": args.compute_backend,
        "sample_count": args.sample_count,
        "fs_hz": args.fs,
        "duration_s": float(_WORKER_T[-1] - _WORKER_T[0]),
        "center_hz": args.center_hz,
        "detector": _WORKER_DETECTOR,
        "weak_amplitude": args.weak_amplitude,
        "runs_per_cell": runs,
        "snr_levels_db": list(snr_levels),
        "amplitude_ratios": [f"1:{value}" for value in amplitude_ratios],
        "separations_hz": list(separations),
        "phase_bins": PHASE_BINS,
        "grid_step_hz": args.grid_step_hz,
        "conditional_threshold": args.conditional_threshold,
        "glrt_mc": args.glrt_mc,
        "glrt_threshold": threshold,
        "max_components": args.max_components,
        "bic_delta": args.bic_delta,
        "target_success": args.target_success,
        "workers": max(1, args.workers),
        "effective_workers": 1 if args.compute_backend in ("cupy_batch", "cupy_full_auto", "cupy_adaptive") else max(1, args.workers),
        "chunksize": args.chunksize,
        "fit_backend": args.compute_backend if args.compute_backend in ("cupy_batch", "cupy_full_auto", "cupy_adaptive") else args.fit_backend,
        "cupy_batch_size": args.cupy_batch_size,
        "cupy_center_span_hz": args.cupy_center_span_hz,
        "cupy_center_step_hz": args.cupy_center_step_hz,
        "cupy_separation_min_hz": args.cupy_separation_min_hz,
        "cupy_separation_max_hz": args.cupy_separation_max_hz,
        "cupy_separation_step_hz": args.cupy_separation_step_hz,
        "cupy_auto_f_min_hz": args.cupy_auto_f_min_hz,
        "cupy_auto_f_max_hz": args.cupy_auto_f_max_hz,
        "cupy_auto_center_span_hz": args.cupy_auto_center_span_hz,
        "cupy_auto_center_step_hz": args.cupy_auto_center_step_hz,
        "cupy_auto_row_batch_size": args.cupy_auto_row_batch_size,
        "cupy_auto_candidate_chunk_size": args.cupy_auto_candidate_chunk_size,
        "adaptive_pilot_runs_per_cell": args.adaptive_pilot_runs_per_cell,
        "adaptive_audit_rate": args.adaptive_audit_rate,
        "adaptive_min_center_span_hz": args.adaptive_min_center_span_hz,
        "adaptive_center_margin_hz": args.adaptive_center_margin_hz,
        "adaptive_max_center_span_hz": args.adaptive_max_center_span_hz,
        "adaptive_audit_frequency_tolerance_hz": args.adaptive_audit_frequency_tolerance_hz,
        "adaptive_fallback_enabled": not args.adaptive_disable_fallback,
        "adaptive_fallback_boundary_ratio": args.adaptive_fallback_boundary_ratio,
        "adaptive_policy_center_offset_hz": args.adaptive_policy_center_offset_hz,
        "adaptive_uses_true_center": False if args.compute_backend == "cupy_adaptive" else None,
        "cupy_run": cupy_run,
        "timing_detail": args.timing_detail,
        "seed": SEED,
        "runtime_seconds": time.perf_counter() - started,
        "paper_pngs": [str(path.name) for path in pngs],
        "surface_summary": surface_summary,
        "phase_summary": phase_summary,
        "limit_summary": limit_summary,
        "timing_summary": timing_summary,
        "command": sys.argv,
    }
    _write_report(paper_dir / "q3_experiment_d_report.md", context)
    (raw_dir / "q3_experiment_d_runtime.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.timing_detail:
        (raw_dir / "q3_experiment_d_timing_summary.json").write_text(json.dumps(timing_summary, ensure_ascii=False, indent=2), encoding="utf-8")
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
            f"Compute backend: `{args.compute_backend}`.",
            "The result is an empirical conditional surface, not a theoretical global resolution limit.",
        ]) + "\n",
        encoding="utf-8",
    )
    print(f"Experiment D complete: {output_dir}")


if __name__ == "__main__":
    main()
