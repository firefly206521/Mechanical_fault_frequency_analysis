"""Resumable Monte Carlo experiments for Q3."""

from __future__ import annotations

import math
import time
from collections.abc import Callable

import numpy as np

from . import SEED
from .core import (
    GLRTConfig,
    golden_minimize,
    close_pair_resolver,
    glrt_scan,
    _multi_sse,
    multi_harmonic_fit,
    music_close_pair,
)


SNR_LEVELS = (-20.0, -15.0, -12.0, -10.0, -5.0)
SEPARATIONS = (0.00025, 0.0005, 0.00075, 0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.0075, 0.01)
AMPLITUDE_CASES = {
    "equal": (0.02, 0.02),
    "unequal": (0.01048, 0.04005),
}


def trial_rng(experiment_id: int, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, experiment_id, replicate]))


def _phase_error(estimate: float, truth: float) -> float:
    return abs(float(np.angle(np.exp(1j * (estimate - truth)))))


def _match_frequencies(estimated: np.ndarray, truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    estimated = np.sort(np.asarray(estimated, float))
    truth = np.sort(np.asarray(truth, float))
    count = min(len(estimated), len(truth))
    return estimated[:count], truth[:count]


def fast_spaced_detection(t: np.ndarray, x: np.ndarray, fs: float, cfg: GLRTConfig, max_components: int = 10) -> dict:
    current = multi_harmonic_fit(t, x, [])
    for _ in range(max_components):
        scan = glrt_scan(current["residual"], fs, cfg, current["parameter_count"])
        if not scan["detected"]:
            break
        coarse = scan["peak_frequency_hz"]
        if len(current["frequencies_hz"]) and np.min(np.abs(current["frequencies_hz"] - coarse)) < 0.002:
            break
        seeds = np.sort(np.r_[current["frequencies_hz"], coarse])
        index = int(np.argmin(np.abs(seeds - coarse)))

        def objective(value: float) -> float:
            candidate = seeds.copy()
            candidate[index] = value
            return _multi_sse(t, x, np.sort(candidate))

        seeds[index] = golden_minimize(objective, max(cfg.f_min, coarse - 0.006), min(cfg.f_max, coarse + 0.006), iterations=30)
        candidate = multi_harmonic_fit(t, x, np.sort(seeds))
        if current["bic"] - candidate["bic"] < 10.0 or candidate["ill_conditioned"]:
            break
        current = candidate
    return current


def run_simulation_trial(
    t: np.ndarray,
    fs: float,
    truth_fit: dict,
    snr_db: float,
    replicate: int,
    cfg: GLRTConfig,
) -> dict:
    truth_f = np.asarray(truth_fit["frequencies_hz"], float)
    truth_a = np.asarray([row["amplitude"] for row in truth_fit["components"]], float)
    truth_phi = np.asarray([row["phase_origin_rad"] for row in truth_fit["components"]], float)
    total_power = float(np.sum(truth_a ** 2 / 2.0))
    noise_std = math.sqrt(total_power / (10.0 ** (snr_db / 10.0)))
    rng = trial_rng(1000 + int(round(snr_db * 10)), replicate)
    phases = rng.uniform(-np.pi, np.pi, len(truth_f))
    signal = np.sum([a * np.sin(2.0 * np.pi * f * t + p) for a, f, p in zip(truth_a, truth_f, phases)], axis=0)
    observed = signal + rng.normal(0.0, noise_std, len(t))
    started = time.perf_counter()
    estimate = fast_spaced_detection(t, observed, fs, cfg)
    elapsed = time.perf_counter() - started
    ef, tf = _match_frequencies(estimate["frequencies_hz"], truth_f)
    frequency_mae = float(np.mean(np.abs(ef - tf))) if len(ef) else float("nan")
    correct_k = len(estimate["frequencies_hz"]) == len(truth_f)
    if correct_k:
        estimated_amplitudes = np.asarray([component["amplitude"] for component in estimate["components"]])
        estimated_phases = np.asarray([component["phase_origin_rad"] for component in estimate["components"]])
        amplitude_relative_error = float(np.mean(np.abs(estimated_amplitudes - truth_a) / truth_a))
        phase_mae = float(np.mean([_phase_error(value, truth) for value, truth in zip(estimated_phases, phases)]))
    else:
        frequency_mae = float("nan")
        amplitude_relative_error = float("nan")
        phase_mae = float("nan")
    recovered = estimate["fit"] - estimate["offset"]
    waveform_rmse = float(np.sqrt(np.mean((recovered - signal) ** 2)))
    row = {
        "snr_total_db": snr_db,
        "replicate": replicate,
        "sample_count": len(t),
        "true_k": len(truth_f),
        "estimated_k": len(estimate["frequencies_hz"]),
        "correct_k": correct_k,
        "frequency_mae_hz": frequency_mae,
        "amplitude_relative_error": amplitude_relative_error,
        "phase_mae_rad": phase_mae,
        "waveform_rmse": waveform_rmse,
        "condition_design": estimate["condition_design"],
        "ill_conditioned": estimate["ill_conditioned"],
        "runtime_seconds": elapsed,
    }
    for index, amplitude in enumerate(truth_a, 1):
        row[f"component_{index}_snr_db"] = 10.0 * math.log10((amplitude ** 2 / 2.0) / noise_std ** 2)
    return row


def run_resolution_trial(
    t: np.ndarray,
    noise_std: float,
    separation: float,
    amplitude_case: str,
    replicate: int,
    music_grid_step: float,
) -> dict:
    amplitudes = AMPLITUDE_CASES[amplitude_case]
    frequencies = np.asarray([13.5 - separation / 2.0, 13.5 + separation / 2.0])
    case_id = 0 if amplitude_case == "equal" else 1
    sep_id = SEPARATIONS.index(separation)
    rng = trial_rng(2000 + 100 * case_id + sep_id, replicate)
    phases = rng.uniform(-np.pi, np.pi, 2)
    signal = sum(a * np.sin(2.0 * np.pi * f * t + p) for a, f, p in zip(amplitudes, frequencies, phases))
    observed = signal + rng.normal(0.0, noise_std, len(t))

    started = time.perf_counter()
    main = close_pair_resolver(t, observed)
    main_seconds = time.perf_counter() - started
    started = time.perf_counter()
    music = music_close_pair(t, observed, grid_step_hz=music_grid_step)
    music_seconds = time.perf_counter() - started

    main_f, true_f = _match_frequencies(main["frequencies_hz"], frequencies)
    music_f, _ = _match_frequencies(music["frequencies_hz"], frequencies)
    tolerance = separation / 4.0
    main_error = float(np.max(np.abs(main_f - true_f))) if len(main_f) == 2 else float("nan")
    music_error = float(np.max(np.abs(music_f - true_f))) if len(music_f) == 2 else float("nan")
    main_success = bool(main["estimated_k"] == 2 and main_error <= tolerance and not main["ill_conditioned"])
    music_success = bool(music["estimated_k"] == 2 and music_error <= tolerance)
    row = {
        "amplitude_case": amplitude_case,
        "separation_hz": separation,
        "replicate": replicate,
        "sample_count": len(t),
        "amplitude_1": amplitudes[0],
        "amplitude_2": amplitudes[1],
        "component_1_snr_db": 10.0 * math.log10((amplitudes[0] ** 2 / 2.0) / noise_std ** 2),
        "component_2_snr_db": 10.0 * math.log10((amplitudes[1] ** 2 / 2.0) / noise_std ** 2),
        "main_estimated_k": main["estimated_k"],
        "main_max_frequency_error_hz": main_error,
        "main_success": main_success,
        "main_bic_improvement": main["bic_improvement"],
        "condition_design": main["condition_design"],
        "condition_normal": main["condition_normal"],
        "smallest_singular_value": main["smallest_singular_value"],
        "numerical_rank": main["numerical_rank"],
        "column_count": main["column_count"],
        "ill_conditioned": main["ill_conditioned"],
        "music_estimated_k": music["estimated_k"],
        "music_max_frequency_error_hz": music_error,
        "music_success": music_success,
        "music_grid_step_hz": music_grid_step,
        "main_runtime_seconds": main_seconds,
        "music_runtime_seconds": music_seconds,
    }
    row["main_frequency_1_hz"] = float(main_f[0]) if len(main_f) >= 1 else float("nan")
    row["main_frequency_2_hz"] = float(main_f[1]) if len(main_f) >= 2 else float("nan")
    row["music_frequency_1_hz"] = float(music_f[0]) if len(music_f) >= 1 else float("nan")
    row["music_frequency_2_hz"] = float(music_f[1]) if len(music_f) >= 2 else float("nan")
    return row


def run_null_trial(t: np.ndarray, fs: float, noise_std: float, replicate: int, cfg: GLRTConfig) -> dict:
    rng = trial_rng(3000, replicate)
    noise = rng.normal(0.0, noise_std, len(t))
    started = time.perf_counter()
    scan = glrt_scan(noise, fs, cfg, 1)
    return {
        "replicate": replicate,
        "sample_count": len(t),
        "glrt_score": scan["peak_score"],
        "glrt_threshold": scan["threshold"],
        "false_alarm": scan["detected"],
        "runtime_seconds": time.perf_counter() - started,
    }


def wilson_interval(successes: int, runs: int, z: float = 1.96) -> tuple[float, float]:
    if runs == 0:
        return float("nan"), float("nan")
    p = successes / runs
    denom = 1.0 + z * z / runs
    center = (p + z * z / (2 * runs)) / denom
    half = z * math.sqrt(p * (1 - p) / runs + z * z / (4 * runs * runs)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def summarize_simulation(rows: list[dict]) -> list[dict]:
    output = []
    for snr in SNR_LEVELS:
        group = [row for row in rows if float(row["snr_total_db"]) == snr]
        if not group:
            continue
        correct = sum(str(row["correct_k"]).lower() == "true" for row in group)
        low, high = wilson_interval(correct, len(group))
        frequency = [float(row["frequency_mae_hz"]) for row in group if np.isfinite(float(row["frequency_mae_hz"]))]
        amplitude = [float(row["amplitude_relative_error"]) for row in group if np.isfinite(float(row["amplitude_relative_error"]))]
        phase = [float(row["phase_mae_rad"]) for row in group if np.isfinite(float(row["phase_mae_rad"]))]
        output.append({
            "snr_total_db": snr,
            "runs": len(group),
            "correct_k_rate": correct / len(group),
            "correct_k_ci95_low": low,
            "correct_k_ci95_high": high,
            "mean_frequency_mae_hz_given_correct_k": float(np.mean(frequency)) if frequency else float("nan"),
            "mean_amplitude_relative_error_given_correct_k": float(np.mean(amplitude)) if amplitude else float("nan"),
            "mean_phase_mae_rad_given_correct_k": float(np.mean(phase)) if phase else float("nan"),
            "mean_waveform_rmse": float(np.mean([float(row["waveform_rmse"]) for row in group])),
            "mean_runtime_seconds": float(np.mean([float(row["runtime_seconds"]) for row in group])),
        })
    return output


def summarize_resolution(rows: list[dict]) -> list[dict]:
    output = []
    for case in AMPLITUDE_CASES:
        for separation in SEPARATIONS:
            group = [row for row in rows if row["amplitude_case"] == case and float(row["separation_hz"]) == separation]
            if not group:
                continue
            main_count = sum(str(row["main_success"]).lower() == "true" for row in group)
            music_count = sum(str(row["music_success"]).lower() == "true" for row in group)
            main_low, main_high = wilson_interval(main_count, len(group))
            music_low, music_high = wilson_interval(music_count, len(group))
            output.append({
                "amplitude_case": case,
                "separation_hz": separation,
                "rayleigh_multiples": separation * 400.0,
                "runs": len(group),
                "main_success_rate": main_count / len(group),
                "main_ci95_low": main_low,
                "main_ci95_high": main_high,
                "music_success_rate": music_count / len(group),
                "music_ci95_low": music_low,
                "music_ci95_high": music_high,
                "median_condition_design": float(np.median([float(row["condition_design"]) for row in group])),
                "max_condition_design": float(np.max([float(row["condition_design"]) for row in group])),
                "ill_conditioned_rate": float(np.mean([str(row["ill_conditioned"]).lower() == "true" for row in group])),
                "mean_main_runtime_seconds": float(np.mean([float(row["main_runtime_seconds"]) for row in group])),
                "mean_music_runtime_seconds": float(np.mean([float(row["music_runtime_seconds"]) for row in group])),
                "priority_for_more_runs": bool(main_low <= 0.90 <= main_high),
            })
    return output


def empirical_limit(summary: list[dict], case: str, method: str = "main", threshold: float = 0.90) -> float | None:
    rows = sorted((row for row in summary if row["amplitude_case"] == case), key=lambda row: row["separation_hz"])
    key = f"{method}_success_rate"
    for index, row in enumerate(rows):
        if row[key] >= threshold and sum(later[key] < threshold for later in rows[index:]) <= 1:
            return float(row["separation_hz"])
    return None
