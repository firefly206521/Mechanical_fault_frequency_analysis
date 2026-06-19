"""Numerical core for Q3 multi-source sinusoid separation.

The module reuses the Q1 GLRT calibration and Q2 preprocessing/statistical
helpers without modifying either earlier question.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import openpyxl

from q2_harmonic_recovery.core import (
    analytic_signal,
    golden_minimize,
    linear_detrend,
    wrap_phase,
)


SPLIT_MULTIPLIERS = np.asarray([0.10, 0.15, 0.25, 0.40, 0.65, 1.00, 1.50, 2.00])


@dataclass(frozen=True)
class GLRTConfig:
    """Dependency-light copy of the current Q1 GLRT parameter interface."""

    f_min: float = 0.05
    f_max: float = 49.5
    p_fa: float = 0.005
    glrt_mc: int = 500
    random_seed: int = 20260620


def q1_compatible_glrt_stat(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    index = np.arange(len(x), dtype=float)
    centered_index = index - np.mean(index)
    centered_x = x - np.mean(x)
    slope = float(np.dot(centered_index, centered_x) / np.dot(centered_index, centered_index))
    y = centered_x - slope * centered_index
    spec = np.fft.rfft(y)
    frequencies = np.fft.rfftfreq(len(y), 1.0 / fs)
    statistic = 2.0 * np.abs(spec) ** 2 / (len(y) * np.var(y) + np.finfo(float).eps)
    return frequencies, statistic


@lru_cache(maxsize=16)
def q1_compatible_glrt_threshold(n: int, fs: float, cfg: GLRTConfig) -> float:
    rng = np.random.default_rng(cfg.random_seed)
    maxima = np.empty(cfg.glrt_mc)
    for index in range(cfg.glrt_mc):
        frequencies, statistic = q1_compatible_glrt_stat(rng.normal(0.0, 1.0, n), fs)
        mask = (frequencies >= cfg.f_min) & (frequencies <= cfg.f_max)
        maxima[index] = float(np.max(statistic[mask]))
    return float(np.quantile(maxima, 1.0 - cfg.p_fa))


def load_multi_source(path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["多故障源"] if "多故障源" in wb.sheetnames else wb.worksheets[1]
    rows = [(row[0], row[1]) for row in ws.iter_rows(min_row=2, values_only=True)]
    wb.close()
    data = np.asarray(rows, dtype=float)
    t, x = data[:, 0], data[:, 1]
    fs = float(1.0 / np.median(np.diff(t)))
    return t, x, fs


def _design_matrix(t: np.ndarray, frequencies: Iterable[float]) -> tuple[np.ndarray, float]:
    frequencies = np.asarray(list(frequencies), dtype=float)
    center = float(np.mean(t))
    tc = t - center
    columns = []
    for frequency in frequencies:
        angle = 2.0 * np.pi * frequency * tc
        columns.extend([np.sin(angle), np.cos(angle)])
    columns.append(np.ones_like(t))
    return np.column_stack(columns), center


def design_diagnostics(design: np.ndarray, rcond: float = 1e-12) -> dict:
    norms = np.linalg.norm(design, axis=0)
    scaled = design / np.maximum(norms, np.finfo(float).eps)
    singular = np.linalg.svd(scaled, compute_uv=False)
    threshold = rcond * singular[0]
    rank = int(np.sum(singular > threshold))
    condition = float(singular[0] / max(singular[-1], np.finfo(float).tiny))
    return {
        "condition_design": condition,
        "condition_normal": condition * condition,
        "smallest_singular_value": float(singular[-1]),
        "numerical_rank": rank,
        "column_count": design.shape[1],
        "ill_conditioned": bool(condition > 1e6 or rank < design.shape[1]),
        "warning_conditioned": bool(condition > 1e4),
    }


def multi_harmonic_fit(t: np.ndarray, y: np.ndarray, frequencies: Iterable[float]) -> dict:
    frequencies = np.sort(np.asarray(list(frequencies), dtype=float))
    design, center = _design_matrix(t, frequencies)
    beta, _, rank, _ = np.linalg.lstsq(design, y, rcond=1e-12)
    fitted = design @ beta
    residual = y - fitted
    diagnostics = design_diagnostics(design)
    diagnostics["lstsq_rank"] = int(rank)
    components = []
    for index, frequency in enumerate(frequencies):
        a, b = map(float, beta[2 * index:2 * index + 2])
        amplitude = float(np.hypot(a, b))
        phase_center = float(math.atan2(b, a))
        phase_origin = float(wrap_phase(phase_center - 2.0 * np.pi * frequency * center))
        component = a * design[:, 2 * index] + b * design[:, 2 * index + 1]
        components.append({
            "component_id": index + 1,
            "frequency_hz": float(frequency),
            "a_centered": a,
            "b_centered": b,
            "amplitude": amplitude,
            "phase_origin_rad": phase_origin,
            "waveform": component,
        })
    n = len(y)
    k = len(frequencies)
    parameter_count = 3 * k + 1
    sse = float(np.dot(residual, residual))
    bic = float(n * math.log(max(sse / n, 1e-300)) + parameter_count * math.log(n))
    return {
        "frequencies_hz": frequencies,
        "components": components,
        "offset": float(beta[-1]),
        "fit": fitted,
        "residual": residual,
        "sse": sse,
        "rmse": float(np.sqrt(sse / n)),
        "bic": bic,
        "parameter_count": parameter_count,
        "explained_variance": float(1.0 - np.var(residual) / np.var(y)),
        **diagnostics,
    }


def _multi_sse(t: np.ndarray, y: np.ndarray, frequencies: Iterable[float]) -> float:
    design, _ = _design_matrix(t, frequencies)
    beta = np.linalg.lstsq(design, y, rcond=1e-12)[0]
    residual = y - design @ beta
    return float(np.dot(residual, residual))


def refine_joint_frequencies(
    t: np.ndarray,
    y: np.ndarray,
    seeds: Iterable[float],
    half_width: float | Iterable[float] = 0.006,
    maxiter: int = 45,
) -> dict:
    seeds = np.sort(np.asarray(list(seeds), dtype=float))
    if len(seeds) == 0:
        return multi_harmonic_fit(t, y, [])
    widths = np.full(len(seeds), float(half_width)) if np.isscalar(half_width) else np.asarray(list(half_width), float)
    base_bounds = [(max(0.001, f - w), f + w) for f, w in zip(seeds, widths)]
    frequencies = seeds.copy()
    previous = frequencies.copy()
    sweeps = min(4, max(2, maxiter // 8))
    for _ in range(sweeps):
        for index in range(len(frequencies)):
            lo, hi = base_bounds[index]
            if index > 0:
                lo = max(lo, frequencies[index - 1] + 1e-7)
            if index + 1 < len(frequencies):
                hi = min(hi, frequencies[index + 1] - 1e-7)
            if hi <= lo:
                continue
            def objective(value: float) -> float:
                candidate = frequencies.copy()
                candidate[index] = value
                return _multi_sse(t, y, candidate)
            frequencies[index] = golden_minimize(objective, lo, hi, iterations=28)
        if np.max(np.abs(frequencies - previous)) < 1e-9:
            break
        previous = frequencies.copy()
    fit = multi_harmonic_fit(t, y, frequencies)
    fit["optimizer_success"] = True
    fit["optimizer_message"] = "bounded coordinate golden-section refinement"
    return fit


def glrt_scan(residual: np.ndarray, fs: float, cfg: GLRTConfig, fitted_parameter_count: int) -> dict:
    frequencies, statistic = q1_compatible_glrt_stat(residual, fs)
    mask = (frequencies >= cfg.f_min) & (frequencies <= cfg.f_max)
    corrected = statistic * max(len(residual) - fitted_parameter_count, 1) / len(residual)
    indexes = np.where(mask)[0]
    local = indexes[(corrected[indexes] >= np.roll(corrected, 1)[indexes]) & (corrected[indexes] > np.roll(corrected, -1)[indexes])]
    if len(local) == 0:
        local = indexes
    order = local[np.argsort(corrected[local])[::-1]]
    threshold = q1_compatible_glrt_threshold(len(residual), fs, cfg)
    return {
        "frequencies": frequencies,
        "statistic": corrected,
        "peak_indexes": order,
        "peak_frequency_hz": float(frequencies[order[0]]),
        "peak_score": float(corrected[order[0]]),
        "threshold": float(threshold),
        "detected": bool(corrected[order[0]] >= threshold),
    }


def _candidate_seed_sets(current: np.ndarray, new_peak: float, duration: float) -> list[tuple[str, np.ndarray]]:
    candidates: list[tuple[str, np.ndarray]] = []
    if len(current) == 0 or np.min(np.abs(current - new_peak)) > 1e-7:
        candidates.append(("residual_peak", np.sort(np.r_[current, new_peak])))
    for index, center in enumerate(current):
        for multiplier in SPLIT_MULTIPLIERS:
            separation = float(multiplier / duration)
            pair = np.asarray([center - separation / 2.0, center + separation / 2.0])
            seed = np.sort(np.r_[np.delete(current, index), pair])
            candidates.append((f"split_{multiplier:.2f}_over_T", seed))
    return candidates


def detect_multitone(
    t: np.ndarray,
    y: np.ndarray,
    fs: float,
    cfg: GLRTConfig,
    max_components: int = 10,
    bic_delta: float = 10.0,
) -> tuple[dict, list[dict]]:
    current = multi_harmonic_fit(t, y, [])
    history: list[dict] = []
    duration = float(t[-1] - t[0])
    for iteration in range(1, max_components + 1):
        scan = glrt_scan(current["residual"], fs, cfg, current["parameter_count"])
        record = {
            "iteration": iteration,
            "components_before": len(current["frequencies_hz"]),
            "residual_peak_hz": scan["peak_frequency_hz"],
            "glrt_score": scan["peak_score"],
            "glrt_threshold": scan["threshold"],
            "glrt_passed": scan["detected"],
            "bic_before": current["bic"],
        }
        if not scan["detected"]:
            record.update({"accepted": False, "stop_reason": "GLRT below threshold"})
            history.append(record)
            break
        seed_sets = _candidate_seed_sets(current["frequencies_hz"], scan["peak_frequency_hz"], duration)
        quick = []
        for origin, seeds in seed_sets:
            if len(seeds) > max_components or np.min(seeds) <= cfg.f_min or np.max(seeds) >= cfg.f_max:
                continue
            trial = multi_harmonic_fit(t, y, seeds)
            quick.append((trial["bic"], origin, seeds))
        quick.sort(key=lambda item: item[0])
        refined = []
        # Quick BIC screening is cheap; only the best seed receives the costly
        # full joint refinement. Close-pair experiments use their dedicated
        # exhaustive split resolver below.
        for _, origin, seeds in quick[:1]:
            widths = np.full(len(seeds), max(3.0 / duration, 0.003))
            trial = refine_joint_frequencies(t, y, seeds, widths)
            refined.append((trial["bic"], origin, trial))
        if not refined:
            record.update({"accepted": False, "stop_reason": "no valid candidate"})
            history.append(record)
            break
        _, origin, best = min(refined, key=lambda item: item[0])
        improvement = current["bic"] - best["bic"]
        accepted = bool(improvement >= bic_delta and not best["ill_conditioned"])
        record.update({
            "candidate_origin": origin,
            "candidate_frequencies_hz": ";".join(f"{f:.12g}" for f in best["frequencies_hz"]),
            "bic_after": best["bic"],
            "bic_improvement": improvement,
            "condition_design": best["condition_design"],
            "accepted": accepted,
            "stop_reason": "accepted" if accepted else ("ill-conditioned" if best["ill_conditioned"] else "BIC improvement below 10"),
        })
        history.append(record)
        if not accepted:
            break
        current = best
    return current, history


def component_table(fit: dict) -> list[dict]:
    noise_power = float(np.mean(fit["residual"] ** 2))
    rows = []
    for component in fit["components"]:
        signal_power = component["amplitude"] ** 2 / 2.0
        rows.append({
            "component_id": component["component_id"],
            "frequency_hz": component["frequency_hz"],
            "amplitude": component["amplitude"],
            "phase_origin_rad": component["phase_origin_rad"],
            "component_snr_db": 10.0 * math.log10(signal_power / noise_power),
            "condition_design": fit["condition_design"],
            "condition_normal": fit["condition_normal"],
            "ill_conditioned": fit["ill_conditioned"],
        })
    return rows


def segment_stability(t: np.ndarray, y: np.ndarray, frequencies: np.ndarray, seconds: float = 50.0) -> list[dict]:
    fs = 1.0 / np.median(np.diff(t))
    size = int(round(seconds * fs))
    rows = []
    for segment_id, start in enumerate(range(0, len(y) - size + 1, size), 1):
        end = start + size
        st, sy = t[start:end], y[start:end]
        common = multi_harmonic_fit(st, sy, frequencies)
        independent = refine_joint_frequencies(st, sy, frequencies, half_width=0.01, maxiter=25)
        for index, (base, refined, component) in enumerate(zip(frequencies, independent["frequencies_hz"], common["components"]), 1):
            rows.append({
                "segment_id": segment_id,
                "start_s": float(st[0]),
                "end_s": float(st[-1]),
                "component_id": index,
                "common_frequency_hz": float(base),
                "independent_frequency_hz": float(refined),
                "frequency_deviation_hz": float(refined - base),
                "amplitude": component["amplitude"],
                "phase_origin_rad": component["phase_origin_rad"],
                "residual_std": float(np.std(common["residual"])),
            })
    return rows


def baseband_series(t: np.ndarray, x: np.ndarray, center_hz: float = 13.5, target_fs: float = 1.0) -> tuple[np.ndarray, np.ndarray, float]:
    analytic = analytic_signal(x)
    mixed = analytic * np.exp(-1j * 2.0 * np.pi * center_hz * t)
    fs = 1.0 / np.median(np.diff(t))
    freq = np.fft.fftfreq(len(t), 1.0 / fs)
    af = np.abs(freq)
    weight = np.zeros_like(freq)
    weight[af <= 0.03] = 1.0
    taper = (af > 0.03) & (af < 0.05)
    weight[taper] = 0.5 * (1.0 + np.cos(np.pi * (af[taper] - 0.03) / 0.02))
    filtered = np.fft.ifft(np.fft.fft(mixed) * weight)
    factor = max(1, int(round(fs / target_fs)))
    return t[::factor], filtered[::factor], fs / factor


def _complex_fit(t: np.ndarray, z: np.ndarray, offsets: Iterable[float]) -> dict:
    offsets = np.sort(np.asarray(list(offsets), dtype=float))
    columns = [np.exp(1j * 2.0 * np.pi * offset * t) for offset in offsets]
    columns.append(np.ones_like(t, dtype=complex))
    design = np.column_stack(columns)
    beta, _, rank, _ = np.linalg.lstsq(design, z, rcond=1e-12)
    residual = z - design @ beta
    diag = design_diagnostics(design)
    n_real = 2 * len(z)
    parameter_count = 3 * len(offsets) + 2
    sse = float(np.sum(np.abs(residual) ** 2))
    bic = float(n_real * math.log(max(sse / n_real, 1e-300)) + parameter_count * math.log(n_real))
    return {"offsets": offsets, "beta": beta, "residual": residual, "sse": sse, "bic": bic, "rank": int(rank), **diag}


def _complex_sse(t: np.ndarray, z: np.ndarray, offsets: Iterable[float]) -> float:
    offsets = np.asarray(list(offsets), dtype=float)
    design = np.column_stack([*[np.exp(1j * 2.0 * np.pi * offset * t) for offset in offsets], np.ones_like(t, dtype=complex)])
    beta = np.linalg.lstsq(design, z, rcond=1e-12)[0]
    residual = z - design @ beta
    return float(np.sum(np.abs(residual) ** 2))


def close_pair_resolver(t: np.ndarray, x: np.ndarray, center_hz: float = 13.5) -> dict:
    tb, z, fsb = baseband_series(t, x, center_hz)
    objective1 = lambda value: _complex_sse(tb, z, [float(value)])
    one_frequency = golden_minimize(objective1, -0.01, 0.01, iterations=35)
    one = _complex_fit(tb, z, [one_frequency])
    duration = float(t[-1] - t[0])
    seeds = [np.asarray([-m / (2 * duration), m / (2 * duration)]) for m in SPLIT_MULTIPLIERS]
    quick = sorted((_complex_fit(tb, z, seed)["bic"], seed) for seed in seeds)
    best_seed = quick[0][1]

    values = best_seed.copy()
    for _ in range(5):
        left_hi = min(-1e-7, values[1] - 1e-7)
        values[0] = golden_minimize(lambda value: _complex_sse(tb, z, [value, values[1]]), -0.012, left_hi, iterations=28)
        right_lo = max(1e-7, values[0] + 1e-7)
        values[1] = golden_minimize(lambda value: _complex_sse(tb, z, [values[0], value]), right_lo, 0.012, iterations=28)
    two = _complex_fit(tb, z, np.sort(values))
    frequencies = center_hz + two["offsets"]
    full_fit = multi_harmonic_fit(t, x, frequencies)
    improvement = one["bic"] - two["bic"]
    accepted = bool(improvement >= 10.0 and not full_fit["ill_conditioned"])
    return {
        "estimated_k": 2 if accepted else 1,
        "frequencies_hz": frequencies if accepted else np.asarray([center_hz + one["offsets"][0]]),
        "bic_one": one["bic"],
        "bic_two": two["bic"],
        "bic_improvement": improvement,
        "condition_design": full_fit["condition_design"],
        "condition_normal": full_fit["condition_normal"],
        "smallest_singular_value": full_fit["smallest_singular_value"],
        "numerical_rank": full_fit["numerical_rank"],
        "column_count": full_fit["column_count"],
        "ill_conditioned": full_fit["ill_conditioned"],
        "baseband_fs_hz": fsb,
    }


def music_close_pair(
    t: np.ndarray,
    x: np.ndarray,
    center_hz: float = 13.5,
    grid_step_hz: float = 0.000025,
    order: int = 80,
) -> dict:
    tb, z, _ = baseband_series(t, x, center_hz)
    order = min(order, len(z) // 2)
    trajectory = np.lib.stride_tricks.sliding_window_view(z, order).T
    snapshots = trajectory.shape[1]
    covariance = trajectory @ trajectory.conj().T / snapshots
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    eigenvalues = np.maximum(eigenvalues.real, 1e-300)
    mdl = []
    for k in range(0, min(4, order - 1) + 1):
        noise_values = eigenvalues[:order - k]
        ratio = np.exp(np.mean(np.log(noise_values))) / np.mean(noise_values)
        value = -snapshots * (order - k) * math.log(max(ratio, 1e-300)) + 0.5 * k * (2 * order - k) * math.log(snapshots)
        mdl.append(value)
    estimated_k = int(np.argmin(mdl))
    grid = np.arange(-0.0075, 0.0075 + grid_step_hz / 2, grid_step_hz)
    if estimated_k < 1:
        return {"estimated_k": 0, "frequencies_hz": np.asarray([]), "grid_step_hz": grid_step_hz, "mdl": mdl}
    signal_space = eigenvectors[:, -estimated_k:]
    steering = np.exp(1j * 2.0 * np.pi * np.arange(order)[:, None] * tb[1] * grid[None, :])
    denominator = order - np.sum(np.abs(signal_space.conj().T @ steering) ** 2, axis=0)
    pseudo = 1.0 / np.maximum(denominator.real, 1e-15)
    peaks = np.where((pseudo[1:-1] > pseudo[:-2]) & (pseudo[1:-1] >= pseudo[2:]))[0] + 1
    peaks = peaks[np.argsort(pseudo[peaks])[::-1]] if len(peaks) else np.asarray([int(np.argmax(pseudo))])
    selected = np.sort(peaks[:min(estimated_k, 2)])
    return {
        "estimated_k": int(len(selected)),
        "frequencies_hz": center_hz + grid[selected],
        "grid_step_hz": grid_step_hz,
        "mdl": mdl,
        "grid_hz": center_hz + grid,
        "pseudospectrum": pseudo,
    }
