"""Numerical core for Q4 V1 adaptive sensor layout.

V1 is a parameterized structural example. Coordinates are dimensionless
surface coordinates, not real machine installation coordinates.
"""

from __future__ import annotations

import itertools
import math
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np

from . import SEED


FAULT_LABELS = ("4Hz", "8Hz", "13Hz", "14Hz")
DEFAULT_FREQUENCIES = np.asarray([3.999998173832588, 7.9999285714666994, 13.00008888535092, 14.000023485389158])
DEFAULT_AMPLITUDES = np.asarray([0.01910292277864388, 0.024889351734884123, 0.010502919663465827, 0.04005274094917999])
REGION_NAMES = (
    "bearing_zone_left",
    "bearing_zone_right",
    "gearbox_zone_left",
    "gearbox_zone_right",
    "input_shaft_zone",
    "output_shaft_zone",
)


@dataclass(frozen=True)
class Q4V1Config:
    fs: float = 100.0
    duration_s: float = 30.0
    p_fa: float = 0.05
    threshold_mc: int = 80
    random_seed: int = SEED
    redundancy_limit: float = 0.97
    prescreen_max: int = 40
    prescreen_min: int = 20
    weight_mean_lambda: float = 0.10
    weight_trace_info: float = 0.002
    weight_min_eigen: float = 0.002
    weight_redundancy: float = -0.03
    eig_regularization: float = 1e-8
    similarity_floor: float = 1e-12
    swap_max_iter_factor: int = 3
    response_gain_jitter: float = 0.0
    response_phase_jitter: float = 0.0
    noise_correlation: float = 0.0
    response_jitter_mode: str = "sensor"
    validation_weight_pd: float = 0.45
    validation_weight_low_snr: float = 0.35
    validation_weight_min_pd: float = 0.20
    validation_weight_fa_excess: float = -2.0


@dataclass(frozen=True)
class CandidatePoint:
    point_id: str
    region: str
    x: float
    y: float
    z: float
    nx: float
    ny: float
    nz: float
    noise_std: float
    installable: bool
    response: tuple[complex, ...]


@dataclass(frozen=True)
class LayoutEvaluation:
    layout: tuple[int, ...]
    objective: float
    robust_min_lambda: float
    raw_mean_lambda: float
    detection_min_lambda: float
    detection_mean_lambda: float
    trace_info: float
    logdet_info: float
    min_eigen_info: float
    redundancy: float


def default_time_axis(cfg: Q4V1Config) -> np.ndarray:
    n = int(round(cfg.duration_s * cfg.fs))
    return np.arange(n, dtype=float) / cfg.fs


def basis_matrices(t: np.ndarray, frequencies: np.ndarray = DEFAULT_FREQUENCIES) -> tuple[np.ndarray, np.ndarray]:
    angle = 2.0 * np.pi * np.asarray(frequencies, float)[:, None] * t[None, :]
    return np.sin(angle), np.cos(angle)


def signal_power(amplitudes: np.ndarray = DEFAULT_AMPLITUDES) -> float:
    return float(np.sum(np.asarray(amplitudes, float) ** 2 / 2.0))


def trial_rng(experiment_id: int, replicate: int, seed: int = SEED) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([seed, experiment_id, replicate]))


def _region_centers() -> dict[str, np.ndarray]:
    return {
        "bearing_zone_left": np.asarray([-1.00, -0.45, 0.18]),
        "bearing_zone_right": np.asarray([1.00, -0.42, 0.16]),
        "gearbox_zone_left": np.asarray([-0.48, 0.42, 0.52]),
        "gearbox_zone_right": np.asarray([0.52, 0.45, 0.50]),
        "input_shaft_zone": np.asarray([-1.25, 0.10, -0.12]),
        "output_shaft_zone": np.asarray([1.25, 0.12, -0.10]),
    }


def _source_locations() -> np.ndarray:
    return np.asarray([
        [-1.10, -0.18, 0.02],
        [0.95, -0.16, 0.04],
        [-0.28, 0.65, 0.32],
        [0.58, 0.68, 0.34],
    ])


def _surface_normal(position: np.ndarray) -> np.ndarray:
    normal = np.asarray([0.18 * position[0], 0.25 * position[1], 1.0])
    return normal / np.linalg.norm(normal)


def _response_at(position: np.ndarray, normal: np.ndarray, region_index: int) -> np.ndarray:
    sources = _source_locations()
    response = np.zeros(len(DEFAULT_FREQUENCIES), dtype=complex)
    for fault_index, frequency in enumerate(DEFAULT_FREQUENCIES):
        vector = position - sources[fault_index]
        distance = float(np.linalg.norm(vector) + 0.20)
        direction_gain = 0.55 + 0.45 * abs(float(np.dot(normal, vector / distance)))
        modal = 1.0 + 0.20 * math.cos((region_index + 1) * (fault_index + 1) * 0.73)
        attenuation = math.exp(-0.38 * distance) / (distance ** 0.65)
        phase = 1.15 * frequency * distance + 0.23 * region_index * (fault_index + 1)
        response[fault_index] = direction_gain * modal * attenuation * np.exp(1j * phase)
    return response


def generate_candidate_points(grid_size: int, seed: int = SEED) -> list[CandidatePoint]:
    rng = np.random.default_rng(seed)
    centers = _region_centers()
    points: list[CandidatePoint] = []
    for index in range(grid_size):
        region_index = index % len(REGION_NAMES)
        region = REGION_NAMES[region_index]
        center = centers[region]
        ring = 0.08 + 0.05 * ((index // len(REGION_NAMES)) % 4)
        angle = 2.0 * np.pi * ((index * 0.61803398875) % 1.0)
        jitter = np.asarray([ring * math.cos(angle), 0.75 * ring * math.sin(angle), 0.035 * rng.normal()])
        position = center + jitter
        normal = _surface_normal(position)
        base_noise = np.asarray([0.95, 1.05, 0.88, 1.20, 1.30, 0.98])[region_index]
        noise_std = float(base_noise * (1.0 + 0.08 * rng.normal()))
        installable = bool((index % 17) != 0 or region in {"gearbox_zone_left", "output_shaft_zone"})
        response = _response_at(position, normal, region_index)
        points.append(CandidatePoint(
            point_id=f"v1_p{index:03d}",
            region=region,
            x=float(position[0]),
            y=float(position[1]),
            z=float(position[2]),
            nx=float(normal[0]),
            ny=float(normal[1]),
            nz=float(normal[2]),
            noise_std=max(noise_std, 0.25),
            installable=installable,
            response=tuple(complex(v) for v in response),
        ))
    return points


def response_matrix(points: list[CandidatePoint]) -> np.ndarray:
    return np.asarray([point.response for point in points], dtype=complex)


def noise_vector(points: list[CandidatePoint]) -> np.ndarray:
    return np.asarray([point.noise_std for point in points], dtype=float)


def fusion_weight_vector(noise_stds: np.ndarray) -> np.ndarray:
    inv_var = 1.0 / np.maximum(np.asarray(noise_stds, dtype=float) ** 2, np.finfo(float).eps)
    return inv_var / np.sum(inv_var)


def whitened_response(points: list[CandidatePoint]) -> np.ndarray:
    return response_matrix(points) / noise_vector(points)[:, None]


def point_scores(points: list[CandidatePoint]) -> list[dict]:
    white = whitened_response(points)
    rows: list[dict] = []
    for index, point in enumerate(points):
        lambdas = (DEFAULT_AMPLITUDES ** 2) * (np.abs(white[index]) ** 2)
        rows.append({
            "point_index": index,
            "point_id": point.point_id,
            "region": point.region,
            "installable": point.installable,
            "noise_std": point.noise_std,
            "min_lambda": float(np.min(lambdas)),
            "raw_mean_lambda": float(np.mean(lambdas)),
            "response_norm": float(np.linalg.norm(white[index])),
            "score": float(np.min(lambdas) + 0.20 * np.mean(lambdas)),
        })
    return rows


def response_similarity(a: np.ndarray, b: np.ndarray, floor: float = 1e-12) -> float:
    denom = float(np.vdot(a, a).real * np.vdot(b, b).real)
    return float(abs(np.vdot(a, b)) ** 2 / max(denom, floor))


def prescreen_points(points: list[CandidatePoint], cfg: Q4V1Config) -> tuple[list[int], list[dict]]:
    scores = point_scores(points)
    installable = [row for row in scores if row["installable"]]
    installable.sort(key=lambda row: row["score"], reverse=True)
    white = whitened_response(points)
    selected: list[int] = []
    selected_regions: set[str] = set()
    target = min(cfg.prescreen_max, max(cfg.prescreen_min, len(points) // 2))
    for row in installable:
        index = int(row["point_index"])
        too_redundant = any(response_similarity(white[index], white[old], cfg.similarity_floor) > cfg.redundancy_limit for old in selected)
        region_needed = len(selected_regions) < min(len(REGION_NAMES), target)
        if not too_redundant or (region_needed and row["region"] not in selected_regions):
            selected.append(index)
            selected_regions.add(str(row["region"]))
        if len(selected) >= target:
            break
    if len(selected) < min(3, len(installable)):
        selected = [int(row["point_index"]) for row in installable[: min(3, len(installable))]]
    if len(selected) < 3:
        raise ValueError("Q4 V1 needs at least three installable candidate points after prescreening")
    selected_set = set(selected)
    for row in scores:
        row["kept_by_prescreen"] = int(row["point_index"]) in selected_set
    return selected, scores


def evaluate_layout(points: list[CandidatePoint], layout: Iterable[int], cfg: Q4V1Config | None = None) -> LayoutEvaluation:
    if cfg is None:
        cfg = Q4V1Config()
    indexes = tuple(int(index) for index in layout)
    if not indexes:
        raise ValueError("layout must contain at least one candidate point")
    h = response_matrix(points)[list(indexes), :]
    sigma = noise_vector(points)[list(indexes)]
    white = h / sigma[:, None]
    lambdas = (DEFAULT_AMPLITUDES ** 2) * np.sum(np.abs(white) ** 2, axis=0)
    fusion_weights = fusion_weight_vector(sigma)
    detection_lambdas = (DEFAULT_AMPLITUDES ** 2) * np.sum(fusion_weights[:, None] * np.abs(white) ** 2, axis=0)
    info = white.conj().T @ white
    regularized_info = info.real + cfg.eig_regularization * np.eye(info.shape[0])
    eigvals = np.maximum(np.linalg.eigvalsh(regularized_info), 0.0)
    redundancy = 0.0
    pairs = 0
    for left, right in itertools.combinations(range(len(indexes)), 2):
        redundancy += response_similarity(white[left], white[right], cfg.similarity_floor)
        pairs += 1
    redundancy = redundancy / pairs if pairs else 0.0
    detection_min = float(np.min(detection_lambdas))
    detection_mean = float(np.mean(detection_lambdas))
    robust_min = float(detection_min * (1.0 - 0.20 * redundancy))
    logdet = float(np.linalg.slogdet(regularized_info)[1])
    min_eig = float(np.min(eigvals))
    trace_info = float(np.trace(info.real))
    redundancy_penalty = redundancy * detection_mean
    objective = (
        robust_min
        + cfg.weight_mean_lambda * detection_mean
        + cfg.weight_trace_info * math.log1p(max(trace_info, 0.0)) * detection_mean
        + cfg.weight_min_eigen * min_eig * detection_mean
        + cfg.weight_redundancy * redundancy_penalty
    )
    return LayoutEvaluation(
        layout=indexes,
        objective=float(objective),
        robust_min_lambda=robust_min,
        raw_mean_lambda=float(np.mean(lambdas)),
        detection_min_lambda=detection_min,
        detection_mean_lambda=detection_mean,
        trace_info=trace_info,
        logdet_info=logdet,
        min_eigen_info=min_eig,
        redundancy=float(redundancy),
    )


def greedy_layout(points: list[CandidatePoint], candidate_indexes: list[int], size: int = 3, cfg: Q4V1Config | None = None) -> LayoutEvaluation:
    if len(candidate_indexes) < size:
        raise ValueError(f"greedy layout needs at least {size} candidate points")
    selected: list[int] = []
    for _ in range(size):
        best: LayoutEvaluation | None = None
        for index in candidate_indexes:
            if index in selected:
                continue
            trial = evaluate_layout(points, [*selected, index], cfg)
            if best is None or trial.objective > best.objective:
                best = trial
        if best is None:
            break
        selected = list(best.layout)
    return evaluate_layout(points, selected, cfg)


def one_swap_search(points: list[CandidatePoint], candidate_indexes: list[int], initial: LayoutEvaluation, cfg: Q4V1Config | None = None) -> LayoutEvaluation:
    if cfg is None:
        cfg = Q4V1Config()
    best = initial
    improved = True
    iteration = 0
    max_iter = max(1, cfg.swap_max_iter_factor * len(candidate_indexes) * max(1, len(initial.layout)))
    while improved and iteration < max_iter:
        iteration += 1
        improved = False
        current = set(best.layout)
        for old in best.layout:
            for new in candidate_indexes:
                if new in current:
                    continue
                trial_layout = tuple(sorted((current - {old}) | {new}))
                trial = evaluate_layout(points, trial_layout, cfg)
                if trial.objective > best.objective + 1e-12:
                    best = trial
                    improved = True
                    break
            if improved:
                break
    if improved:
        warnings.warn("Q4 V1 one_swap_search reached max_iter before convergence", RuntimeWarning, stacklevel=2)
    return best


def exhaustive_layouts(points: list[CandidatePoint], candidate_indexes: list[int], top_n: int = 10, cfg: Q4V1Config | None = None) -> list[LayoutEvaluation]:
    if len(candidate_indexes) < 3:
        raise ValueError("exhaustive layout search needs at least three candidate points")
    evaluations = [evaluate_layout(points, combo, cfg) for combo in itertools.combinations(candidate_indexes, 3)]
    evaluations.sort(key=lambda row: row.objective, reverse=True)
    return evaluations[:top_n]


def layout_name(points: list[CandidatePoint], layout: Iterable[int]) -> str:
    return "+".join(points[index].point_id for index in layout)


def layout_regions(points: list[CandidatePoint], layout: Iterable[int]) -> str:
    return "+".join(points[index].region for index in layout)


def baseline_layouts(points: list[CandidatePoint], candidate_indexes: list[int], seed: int = SEED) -> dict[str, tuple[int, ...]]:
    if len(candidate_indexes) < 3:
        raise ValueError("baseline layouts need at least three candidate points")
    scores = point_scores(points)
    kept = [row for row in scores if int(row["point_index"]) in set(candidate_indexes)]
    kept.sort(key=lambda row: row["score"], reverse=True)
    max_response = tuple(sorted(int(row["point_index"]) for row in kept[:3]))
    rng = np.random.default_rng(seed + 313)
    random_three = tuple(sorted(rng.choice(candidate_indexes, size=3, replace=False).tolist()))
    sorted_by_x = sorted(candidate_indexes, key=lambda index: points[index].x)
    spaced = tuple(sorted(sorted_by_x[index] for index in [0, len(sorted_by_x) // 2, len(sorted_by_x) - 1]))
    v0_regions = ("bearing_zone_left", "gearbox_zone_left", "output_shaft_zone")
    v0_like: list[int] = []
    for region in v0_regions:
        regional = [row for row in kept if row["region"] == region]
        if regional:
            v0_like.append(int(regional[0]["point_index"]))
    if len(v0_like) < 3:
        for row in kept:
            idx = int(row["point_index"])
            if idx not in v0_like:
                v0_like.append(idx)
            if len(v0_like) == 3:
                break
    return {
        "v1_max_response_three": max_response,
        "v1_random_three": random_three,
        "v1_spaced_three": spaced,
        "v1_v0_region_baseline": tuple(sorted(v0_like[:3])),
    }


def noise_stds_for_snr(points: list[CandidatePoint], snr_db: float) -> np.ndarray:
    base_sigma = math.sqrt(signal_power() / (10.0 ** (snr_db / 10.0)))
    return base_sigma * noise_vector(points)


def generate_noise(noise_stds: np.ndarray, sample_count: int, rng: np.random.Generator, correlation: float = 0.0) -> np.ndarray:
    if not 0.0 <= correlation < 1.0:
        raise ValueError("noise correlation must be in [0, 1)")
    independent = rng.normal(0.0, noise_stds[:, None], (len(noise_stds), sample_count))
    if correlation == 0.0 or len(noise_stds) == 1:
        return independent
    shared = rng.normal(0.0, 1.0, sample_count)
    return math.sqrt(1.0 - correlation) * independent + math.sqrt(correlation) * noise_stds[:, None] * shared[None, :]


def perturb_responses(responses: np.ndarray, rng: np.random.Generator, cfg: Q4V1Config) -> np.ndarray:
    if cfg.response_gain_jitter == 0.0 and cfg.response_phase_jitter == 0.0:
        return responses
    if cfg.response_jitter_mode == "sensor":
        shape = (responses.shape[0], 1)
    elif cfg.response_jitter_mode == "element":
        shape = responses.shape
    else:
        raise ValueError("response jitter mode must be 'sensor' or 'element'")
    gain = np.exp(rng.normal(0.0, cfg.response_gain_jitter, shape))
    phase = rng.normal(0.0, cfg.response_phase_jitter, shape)
    return responses * gain * np.exp(1j * phase)


def synthesize_layout_samples(
    points: list[CandidatePoint],
    layout: tuple[int, ...],
    t: np.ndarray,
    snr_db: float,
    rng: np.random.Generator,
    cfg: Q4V1Config,
) -> tuple[np.ndarray, np.ndarray]:
    noise_stds_all = noise_stds_for_snr(points, snr_db)
    noise_stds = noise_stds_all[list(layout)]
    responses = perturb_responses(response_matrix(points)[list(layout), :], rng, cfg)
    phases = rng.uniform(-np.pi, np.pi, len(DEFAULT_FREQUENCIES))
    samples = np.zeros((len(layout), len(t)), dtype=float)
    for sensor_index in range(len(layout)):
        for fault_index, frequency in enumerate(DEFAULT_FREQUENCIES):
            response = responses[sensor_index, fault_index]
            samples[sensor_index] += DEFAULT_AMPLITUDES[fault_index] * abs(response) * np.sin(
                2.0 * np.pi * frequency * t + phases[fault_index] + np.angle(response)
            )
    samples += generate_noise(noise_stds, len(t), rng, cfg.noise_correlation)
    return samples, noise_stds


def projection_statistics(samples: np.ndarray, sin_basis: np.ndarray, cos_basis: np.ndarray, noise_stds: np.ndarray) -> np.ndarray:
    n = samples.shape[1]
    centered = samples - np.mean(samples, axis=1, keepdims=True)
    a = (2.0 / n) * centered @ sin_basis.T
    b = (2.0 / n) * centered @ cos_basis.T
    return n * (a * a + b * b) / (2.0 * (noise_stds[:, None] ** 2 + np.finfo(float).eps))


def fused_statistics(stats: np.ndarray, noise_stds: np.ndarray) -> np.ndarray:
    weights = fusion_weight_vector(noise_stds)
    return np.sum(stats * weights[:, None], axis=0)


@lru_cache(maxsize=512)
def calibrated_threshold(layout_key: tuple[int, ...], noise_key: tuple[float, ...], cfg: Q4V1Config) -> float:
    t = default_time_axis(cfg)
    sin_basis, cos_basis = basis_matrices(t)
    noise_stds = np.asarray(noise_key, dtype=float)
    rng = trial_rng(9100 + len(layout_key), sum(layout_key), cfg.random_seed)
    maxima = np.empty(cfg.threshold_mc, dtype=float)
    for index in range(cfg.threshold_mc):
        noise = generate_noise(noise_stds, len(t), rng, cfg.noise_correlation)
        stats = projection_statistics(noise, sin_basis, cos_basis, noise_stds)
        maxima[index] = float(np.max(fused_statistics(stats, noise_stds)))
    return float(np.quantile(maxima, 1.0 - cfg.p_fa, method="higher"))
