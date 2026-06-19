"""Numerical core for Q4 sensor layout optimization.

The fourth question is a layout problem, so this module keeps the Q1-Q3
detection model fixed and adds a sensor sensitivity/noise layer around it.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np

from . import SEED


SENSOR_NAMES = (
    "bearing_left",
    "bearing_right",
    "gearbox_left",
    "gearbox_right",
    "input_shaft",
    "output_shaft",
)

FAULT_LABELS = ("4Hz", "8Hz", "13Hz", "14Hz")
DEFAULT_FREQUENCIES = np.asarray([3.999998173832588, 7.9999285714666994, 13.00008888535092, 14.000023485389158])
DEFAULT_AMPLITUDES = np.asarray([0.01910292277864388, 0.024889351734884123, 0.010502919663465827, 0.04005274094917999])


@dataclass(frozen=True)
class Q4Config:
    fs: float = 100.0
    duration_s: float = 40.0
    p_fa: float = 0.05
    threshold_mc: int = 500
    lambda_pfa: float = 2.0
    mu_balance: float = 0.5
    random_seed: int = SEED


@dataclass(frozen=True)
class SensorScenario:
    name: str
    description: str
    sensitivity: tuple[tuple[float, ...], ...]
    noise_multiplier: tuple[float, ...]
    phase_offset_rad: tuple[tuple[float, ...], ...]


def default_time_axis(cfg: Q4Config) -> np.ndarray:
    n = int(round(cfg.duration_s * cfg.fs))
    return np.arange(n, dtype=float) / cfg.fs


def base_sensitivity_matrix() -> np.ndarray:
    """Synthetic but interpretable source-to-sensor sensitivity matrix."""
    return np.asarray([
        [0.95, 0.65, 0.35, 0.45],
        [0.60, 0.95, 0.45, 0.50],
        [0.45, 0.55, 1.05, 0.75],
        [0.40, 0.50, 0.80, 1.10],
        [1.10, 0.45, 0.35, 0.25],
        [0.35, 0.50, 0.65, 1.00],
    ], dtype=float)


def base_phase_offsets() -> np.ndarray:
    return np.asarray([
        [0.00, 0.10, -0.05, 0.18],
        [0.20, -0.08, 0.12, -0.10],
        [-0.12, 0.18, 0.00, 0.15],
        [0.16, -0.14, 0.22, 0.00],
        [-0.06, 0.04, -0.18, 0.12],
        [0.11, -0.20, 0.08, -0.04],
    ], dtype=float)


def default_scenarios() -> list[SensorScenario]:
    base_h = base_sensitivity_matrix()
    base_delta = base_phase_offsets()

    skew_noise = np.asarray([0.90, 1.10, 0.85, 1.60, 1.45, 0.95])
    weak_sensor = base_h.copy()
    weak_sensor[3, :] *= 0.35
    weak_sensor[4, 0] *= 0.30

    source_shadow = base_h.copy()
    source_shadow[:, 2] *= np.asarray([0.50, 0.65, 1.00, 0.90, 0.40, 0.75])
    source_shadow[:, 3] *= np.asarray([0.60, 0.55, 0.75, 1.00, 0.35, 0.95])

    phase_diverse = base_delta.copy()
    phase_diverse[:, 2:] += np.asarray([
        [0.70, -0.55],
        [-0.65, 0.50],
        [0.10, -0.20],
        [-0.15, 0.25],
        [0.90, -0.75],
        [-0.45, 0.40],
    ])

    return [
        _scenario("balanced", "敏感度和噪声相对均衡", base_h, np.ones(len(SENSOR_NAMES)), base_delta),
        _scenario("spatial_noise_skew", "齿轮箱右侧和输入轴侧噪声明显偏大", base_h, skew_noise, base_delta),
        _scenario("weak_single_sensor", "部分测点安装耦合差或局部失敏", weak_sensor, np.ones(len(SENSOR_NAMES)), base_delta),
        _scenario("source_shadow", "部分故障源到若干测点传播衰减更强", source_shadow, np.asarray([1.0, 1.05, 0.95, 1.1, 1.1, 0.95]), phase_diverse),
    ]


def _scenario(
    name: str,
    description: str,
    sensitivity: np.ndarray,
    noise_multiplier: np.ndarray,
    phase_offset_rad: np.ndarray,
) -> SensorScenario:
    return SensorScenario(
        name=name,
        description=description,
        sensitivity=tuple(tuple(float(v) for v in row) for row in sensitivity),
        noise_multiplier=tuple(float(v) for v in noise_multiplier),
        phase_offset_rad=tuple(tuple(float(v) for v in row) for row in phase_offset_rad),
    )


def all_layouts(max_sensors: int = 3) -> list[tuple[str, ...]]:
    layouts: list[tuple[str, ...]] = []
    for size in range(1, max_sensors + 1):
        layouts.extend(itertools.combinations(SENSOR_NAMES, size))
    return layouts


def layout_indexes(layout: Iterable[str]) -> tuple[int, ...]:
    lookup = {name: index for index, name in enumerate(SENSOR_NAMES)}
    return tuple(lookup[name] for name in layout)


def trial_rng(experiment_id: int, replicate: int, seed: int = SEED) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([seed, experiment_id, replicate]))


def basis_matrices(t: np.ndarray, frequencies: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    angle = 2.0 * np.pi * np.asarray(frequencies, float)[:, None] * t[None, :]
    return np.sin(angle), np.cos(angle)


def signal_power(amplitudes: np.ndarray) -> float:
    return float(np.sum(np.asarray(amplitudes, float) ** 2 / 2.0))


def noise_stds_for_snr(amplitudes: np.ndarray, snr_db: float, scenario: SensorScenario) -> np.ndarray:
    base_sigma = math.sqrt(signal_power(amplitudes) / (10.0 ** (snr_db / 10.0)))
    return base_sigma * np.asarray(scenario.noise_multiplier, dtype=float)


def synthesize_multisensor(
    t: np.ndarray,
    frequencies: np.ndarray,
    amplitudes: np.ndarray,
    phases: np.ndarray,
    scenario: SensorScenario,
    noise_stds: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    h = np.asarray(scenario.sensitivity, dtype=float)
    delta = np.asarray(scenario.phase_offset_rad, dtype=float)
    sensors = np.zeros((len(SENSOR_NAMES), len(t)), dtype=float)
    for sensor_index in range(len(SENSOR_NAMES)):
        for source_index, (frequency, amplitude, phase) in enumerate(zip(frequencies, amplitudes, phases)):
            sensors[sensor_index] += h[sensor_index, source_index] * amplitude * np.sin(
                2.0 * np.pi * frequency * t + phase + delta[sensor_index, source_index]
            )
        sensors[sensor_index] += rng.normal(0.0, noise_stds[sensor_index], len(t))
    return sensors


def projection_statistics(
    samples: np.ndarray,
    sin_basis: np.ndarray,
    cos_basis: np.ndarray,
    noise_stds: np.ndarray,
) -> np.ndarray:
    """Return per-sensor, per-frequency GLRT-like projection statistics."""
    n = samples.shape[1]
    centered = samples - np.mean(samples, axis=1, keepdims=True)
    a = (2.0 / n) * centered @ sin_basis.T
    b = (2.0 / n) * centered @ cos_basis.T
    return n * (a * a + b * b) / (2.0 * (noise_stds[:, None] ** 2 + np.finfo(float).eps))


def fused_statistics(stats: np.ndarray, layout: tuple[str, ...], noise_stds: np.ndarray) -> np.ndarray:
    indexes = layout_indexes(layout)
    inv_var = 1.0 / np.maximum(noise_stds[list(indexes)] ** 2, np.finfo(float).eps)
    weights = inv_var / np.sum(inv_var)
    return np.sum(stats[list(indexes), :] * weights[:, None], axis=0)


@lru_cache(maxsize=512)
def calibrated_threshold(
    layout: tuple[str, ...],
    scenario: SensorScenario,
    cfg: Q4Config,
) -> float:
    t = default_time_axis(cfg)
    sin_basis, cos_basis = basis_matrices(t, DEFAULT_FREQUENCIES)
    noise_stds = np.asarray(scenario.noise_multiplier, dtype=float)
    rng = trial_rng(9000 + 17 * len(layout), len(layout), cfg.random_seed)
    maxima = np.empty(cfg.threshold_mc, dtype=float)
    for index in range(cfg.threshold_mc):
        noise = rng.normal(0.0, noise_stds[:, None], (len(SENSOR_NAMES), len(t)))
        stats = projection_statistics(noise, sin_basis, cos_basis, noise_stds)
        maxima[index] = float(np.max(fused_statistics(stats, layout, noise_stds)))
    return float(np.quantile(maxima, 1.0 - cfg.p_fa))


def evaluate_detection_trial(
    layout: tuple[str, ...],
    scenario: SensorScenario,
    snr_db: float,
    replicate: int,
    cfg: Q4Config,
    frequencies: np.ndarray = DEFAULT_FREQUENCIES,
    amplitudes: np.ndarray = DEFAULT_AMPLITUDES,
) -> dict:
    t = default_time_axis(cfg)
    sin_basis, cos_basis = basis_matrices(t, frequencies)
    rng = trial_rng(1000 + int(round(10 * snr_db)) + 37 * len(layout), replicate, cfg.random_seed)
    phases = rng.uniform(-np.pi, np.pi, len(frequencies))
    noise_stds = noise_stds_for_snr(amplitudes, snr_db, scenario)
    samples = synthesize_multisensor(t, frequencies, amplitudes, phases, scenario, noise_stds, rng)
    stats = projection_statistics(samples, sin_basis, cos_basis, noise_stds)
    fused = fused_statistics(stats, layout, noise_stds)
    threshold = calibrated_threshold(layout, scenario, cfg)
    source_detected = fused >= threshold
    return {
        "layout": "+".join(layout),
        "sensor_count": len(layout),
        "scenario": scenario.name,
        "snr_db": snr_db,
        "replicate": replicate,
        "threshold": threshold,
        "detected_any": bool(np.any(source_detected)),
        "detected_all": bool(np.all(source_detected)),
        "source_detection_rate": float(np.mean(source_detected)),
        **{f"fault_{index + 1}_detected": bool(value) for index, value in enumerate(source_detected)},
        **{f"fault_{index + 1}_statistic": float(value) for index, value in enumerate(fused)},
    }


def evaluate_false_alarm_trial(
    layout: tuple[str, ...],
    scenario: SensorScenario,
    snr_db: float,
    replicate: int,
    cfg: Q4Config,
) -> dict:
    t = default_time_axis(cfg)
    sin_basis, cos_basis = basis_matrices(t, DEFAULT_FREQUENCIES)
    noise_stds = noise_stds_for_snr(DEFAULT_AMPLITUDES, snr_db, scenario)
    rng = trial_rng(7000 + int(round(10 * snr_db)) + 41 * len(layout), replicate, cfg.random_seed)
    noise = rng.normal(0.0, noise_stds[:, None], (len(SENSOR_NAMES), len(t)))
    stats = projection_statistics(noise, sin_basis, cos_basis, noise_stds)
    fused = fused_statistics(stats, layout, noise_stds)
    threshold = calibrated_threshold(layout, scenario, cfg)
    return {
        "layout": "+".join(layout),
        "sensor_count": len(layout),
        "scenario": scenario.name,
        "snr_db": snr_db,
        "replicate": replicate,
        "threshold": threshold,
        "false_alarm": bool(np.max(fused) >= threshold),
        "max_noise_statistic": float(np.max(fused)),
    }


def score_layout(mean_pd: float, p_fa: float, fault_pd_values: Iterable[float], cfg: Q4Config) -> float:
    balance_var = float(np.var(np.asarray(list(fault_pd_values), dtype=float)))
    return float(mean_pd - cfg.lambda_pfa * p_fa - cfg.mu_balance * balance_var)
