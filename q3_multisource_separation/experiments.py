"""Resumable Monte Carlo experiments for Q3."""

from __future__ import annotations

import math
import time

import numpy as np

from . import SEED
from .core import (
    GLRTConfig,
    close_pair_resolver,
    detect_multitone,
    glrt_scan,
    music_close_pair,
)


SNR_LEVELS = (-22.0, -20.0, -18.0, -16.0, -15.0, -14.0, -12.0, -10.0, -8.0, -6.0, -4.0, -2.0, 0.0)
SEPARATIONS = (0.00025, 0.0005, 0.00075, 0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004, 0.005, 0.0075, 0.01)
AMPLITUDE_CASES = {
    "equal": (0.02, 0.02),
    "unequal": (0.01048, 0.04005),
}
EXTREME_CASES = (
    "very_low_snr_-25",
    "very_low_snr_-30",
    "non_symmetric_close",
    "identical_frequency",
    "phase_cancellation",
    "harmonic_pair",
    "overcomplete_k8",
    "impulsive_noise",
    "low_frequency_boundary",
    "high_frequency_boundary",
)


def trial_rng(experiment_id: int, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([SEED, experiment_id, replicate]))


def _phase_error(estimate: float, truth: float) -> float:
    return abs(float(np.angle(np.exp(1j * (estimate - truth)))))


def _match_frequencies(estimated: np.ndarray, truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    estimated = np.sort(np.asarray(estimated, float))
    truth = np.sort(np.asarray(truth, float))
    count = min(len(estimated), len(truth))
    return estimated[:count], truth[:count]


def fast_spaced_detection(
    t: np.ndarray,
    x: np.ndarray,
    fs: float,
    cfg: GLRTConfig,
    max_components: int = 10,
    bic_delta: float = 10.0,
) -> dict:
    """Compatibility wrapper around the same detector used for real data."""
    fit, _ = detect_multitone(t, x, fs, cfg, max_components=max_components, bic_delta=bic_delta)
    return fit


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
    conditional_threshold: float | None = None,
) -> dict:
    """近频辨识单次试验：双正弦近频分离 + MUSIC 对照。"""
    # [AI-1] 辅助近频网格扫描与 conditional_threshold 条件门限
    amplitudes = AMPLITUDE_CASES[amplitude_case]
    frequencies = np.asarray([13.5 - separation / 2.0, 13.5 + separation / 2.0])
    case_id = 0 if amplitude_case == "equal" else 1
    sep_id = SEPARATIONS.index(separation)
    rng = trial_rng(2000 + 100 * case_id + sep_id, replicate)
    phases = rng.uniform(-np.pi, np.pi, 2)
    signal = sum(a * np.sin(2.0 * np.pi * f * t + p) for a, f, p in zip(amplitudes, frequencies, phases))
    observed = signal + rng.normal(0.0, noise_std, len(t))

    started = time.perf_counter()
    main = close_pair_resolver(
        t,
        observed,
        local_grid_step_hz=music_grid_step,
        conditional_threshold=conditional_threshold,
    )
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
        "main_candidate_origin": main.get("candidate_origin", ""),
        "main_residual_peak_ratio": main.get("residual_peak_ratio", float("nan")),
        "main_conditional_glrt_statistic": main.get("conditional_glrt_statistic", float("nan")),
        "main_conditional_glrt_threshold": main.get("conditional_glrt_threshold", float("nan")),
        "main_frequency_ci_reliable": main.get("frequency_ci_reliable", False),
        "main_frequency_1_se_hz": main.get("frequency_1_se_hz", float("nan")),
        "main_frequency_2_se_hz": main.get("frequency_2_se_hz", float("nan")),
        "main_local_grid_step_hz": main.get("local_grid_step_hz", music_grid_step),
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


def _nearest_mae(estimated: np.ndarray, truth: np.ndarray) -> float:
    estimated = np.asarray(estimated, float)
    truth = np.asarray(truth, float)
    if len(estimated) == 0 or len(truth) == 0:
        return float("nan")
    remaining = list(estimated)
    errors = []
    for value in truth:
        index = int(np.argmin(np.abs(np.asarray(remaining) - value)))
        errors.append(abs(remaining.pop(index) - value))
        if not remaining:
            break
    return float(np.mean(errors))


def _signal_from_components(t: np.ndarray, frequencies: np.ndarray, amplitudes: np.ndarray, phases: np.ndarray) -> np.ndarray:
    return np.sum([a * np.sin(2.0 * np.pi * f * t + p) for a, f, p in zip(amplitudes, frequencies, phases)], axis=0)


def run_extreme_trial(t: np.ndarray, fs: float, truth_fit: dict, noise_std: float, case_name: str, replicate: int, cfg: GLRTConfig) -> dict:
    rng = trial_rng(4000 + EXTREME_CASES.index(case_name), replicate)
    truth_f = np.asarray(truth_fit["frequencies_hz"], float)
    truth_a = np.asarray([row["amplitude"] for row in truth_fit["components"]], float)
    expected_k = None
    success_mode = "correct_k"
    theoretical_identifiable = True
    noise_kind = "gaussian"
    frequency_tolerance = None

    if case_name == "very_low_snr_-25":
        frequencies = truth_f
        amplitudes = truth_a
        phases = rng.uniform(-np.pi, np.pi, len(frequencies))
        total_power = float(np.sum(amplitudes ** 2 / 2.0))
        sigma = math.sqrt(total_power / (10.0 ** (-25.0 / 10.0)))
    elif case_name == "very_low_snr_-30":
        frequencies = truth_f
        amplitudes = truth_a
        phases = rng.uniform(-np.pi, np.pi, len(frequencies))
        total_power = float(np.sum(amplitudes ** 2 / 2.0))
        sigma = math.sqrt(total_power / (10.0 ** (-30.0 / 10.0)))
    elif case_name == "non_symmetric_close":
        frequencies = np.asarray([13.502, 13.505])
        amplitudes = np.asarray([0.04, 0.035])
        phases = rng.uniform(-np.pi, np.pi, 2)
        sigma = noise_std
    elif case_name == "identical_frequency":
        frequencies = np.asarray([13.5, 13.5])
        amplitudes = np.asarray([0.02, 0.02])
        phases = rng.uniform(-np.pi, np.pi, 2)
        sigma = noise_std
        expected_k = 1
        success_mode = "non_identifiable"
        theoretical_identifiable = False
    elif case_name == "phase_cancellation":
        frequencies = np.asarray([13.5, 13.5])
        amplitudes = np.asarray([0.03, 0.03])
        base_phase = rng.uniform(-np.pi, np.pi)
        phases = np.asarray([base_phase, base_phase + np.pi + rng.normal(0.0, 0.03)])
        sigma = noise_std
        expected_k = 1
        success_mode = "non_identifiable"
        theoretical_identifiable = False
    elif case_name == "harmonic_pair":
        frequencies = np.asarray([4.0, 8.0])
        amplitudes = np.asarray([0.019103, 0.024889])
        phases = rng.uniform(-np.pi, np.pi, 2)
        sigma = noise_std
        frequency_tolerance = 0.0025
    elif case_name == "overcomplete_k8":
        frequencies = np.asarray([3.0, 5.5, 8.0, 11.0, 13.0, 16.0, 21.0, 29.0])
        amplitudes = np.asarray([0.035, 0.030, 0.026, 0.023, 0.020, 0.018, 0.016, 0.014])
        phases = rng.uniform(-np.pi, np.pi, len(frequencies))
        total_power = float(np.sum(amplitudes ** 2 / 2.0))
        sigma = math.sqrt(total_power / (10.0 ** (-10.0 / 10.0)))
    elif case_name == "impulsive_noise":
        frequencies = truth_f
        amplitudes = truth_a
        phases = rng.uniform(-np.pi, np.pi, len(frequencies))
        sigma = noise_std
        noise_kind = "gaussian_plus_impulses"
    elif case_name == "low_frequency_boundary":
        frequencies = np.asarray([0.08, 0.12])
        amplitudes = np.asarray([0.04, 0.035])
        phases = rng.uniform(-np.pi, np.pi, 2)
        sigma = noise_std
    elif case_name == "high_frequency_boundary":
        frequencies = np.asarray([48.8, 49.2])
        amplitudes = np.asarray([0.04, 0.035])
        phases = rng.uniform(-np.pi, np.pi, 2)
        sigma = noise_std
    else:
        raise ValueError(f"Unknown extreme case: {case_name}")

    signal = _signal_from_components(t, frequencies, amplitudes, phases)
    noise = rng.normal(0.0, sigma, len(t))
    if noise_kind == "gaussian_plus_impulses":
        spike_count = max(1, len(t) // 200)
        indexes = rng.choice(len(t), size=spike_count, replace=False)
        noise[indexes] += rng.normal(0.0, 12.0 * sigma, spike_count)
    observed = signal + noise

    started = time.perf_counter()
    if case_name in {"non_symmetric_close", "identical_frequency", "phase_cancellation"}:
        estimate = close_pair_resolver(t, observed, conditional_threshold=cfg.conditional_threshold)
    else:
        estimate = fast_spaced_detection(t, observed, fs, cfg)
    elapsed = time.perf_counter() - started
    estimated_f = np.asarray(estimate["frequencies_hz"], float)
    true_k = len(frequencies)
    target_k = expected_k if expected_k is not None else true_k
    frequency_mae = _nearest_mae(estimated_f, frequencies)
    if success_mode == "non_identifiable":
        success = len(estimated_f) <= target_k
    else:
        tolerance = frequency_tolerance if frequency_tolerance is not None else (
            0.0025 if true_k > 2 else max(0.0005, np.min(np.diff(np.sort(frequencies))) / 4.0)
        )
        success = len(estimated_f) == target_k and np.isfinite(frequency_mae) and frequency_mae <= tolerance and not estimate["ill_conditioned"]
    return {
        "case_name": case_name,
        "replicate": replicate,
        "sample_count": len(t),
        "true_k": true_k,
        "expected_k": target_k,
        "estimated_k": len(estimated_f),
        "success": success,
        "frequency_mae_hz": frequency_mae,
        "noise_kind": noise_kind,
        "theoretical_identifiable": theoretical_identifiable,
        "condition_design": estimate["condition_design"],
        "ill_conditioned": estimate["ill_conditioned"],
        "runtime_seconds": elapsed,
        "true_frequencies_hz": ";".join(f"{value:.9g}" for value in frequencies),
        "estimated_frequencies_hz": ";".join(f"{value:.9g}" for value in estimated_f),
        "candidate_origin": estimate.get("candidate_origin", ""),
        "residual_peak_ratio": estimate.get("residual_peak_ratio", float("nan")),
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
        group = [row for row in rows if np.isclose(float(row["snr_total_db"]), snr, rtol=0.0, atol=1e-12)]
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
            group = [row for row in rows if row["amplitude_case"] == case and np.isclose(float(row["separation_hz"]), separation, rtol=0.0, atol=1e-12)]
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


def summarize_extreme(rows: list[dict]) -> list[dict]:
    output = []
    for case_name in EXTREME_CASES:
        group = [row for row in rows if row["case_name"] == case_name]
        if not group:
            continue
        successes = sum(str(row["success"]).lower() == "true" for row in group)
        low, high = wilson_interval(successes, len(group))
        frequency = [float(row["frequency_mae_hz"]) for row in group if np.isfinite(float(row["frequency_mae_hz"]))]
        output.append({
            "case_name": case_name,
            "runs": len(group),
            "success_rate": successes / len(group),
            "success_ci95_low": low,
            "success_ci95_high": high,
            "mean_estimated_k": float(np.mean([int(row["estimated_k"]) for row in group])),
            "median_frequency_mae_hz": float(np.median(frequency)) if frequency else float("nan"),
            "ill_conditioned_rate": float(np.mean([str(row["ill_conditioned"]).lower() == "true" for row in group])),
            "theoretical_identifiable": str(group[0]["theoretical_identifiable"]).lower() == "true",
            "mean_runtime_seconds": float(np.mean([float(row["runtime_seconds"]) for row in group])),
        })
    return output


def empirical_limit(summary: list[dict], case: str, method: str = "main", threshold: float = 0.90) -> float | None:
    rows = sorted((row for row in summary if row["amplitude_case"] == case), key=lambda row: row["separation_hz"])
    key = f"{method}_success_rate"
    for index, row in enumerate(rows):
        if row[key] >= threshold and sum(later[key] < threshold for later in rows[index:]) <= 1:
            return float(row["separation_hz"])
    return None
