"""CuPy batch kernels for Q3 experiment D.

This module is intentionally separate from the CPU detector.  It targets the
experiment-D two-tone close-frequency workload with batched GPU variable
projection, while keeping the existing CPU path as the correctness baseline.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .core import compute_bic, design_diagnostics


@dataclass(frozen=True)
class CupyBatchConfig:
    center_hz: float
    fs: float
    bic_delta: float
    center_span_hz: float = 0.0
    center_step_hz: float = 0.00025
    separation_min_hz: float = 0.0005
    separation_max_hz: float = 0.022
    separation_step_hz: float = 0.00025


@dataclass(frozen=True)
class CupyFullAutoConfig:
    fs: float
    bic_delta: float
    f_min_hz: float = 0.5
    f_max_hz: float = 20.0
    local_center_span_hz: float = 0.006
    local_center_step_hz: float = 0.00025
    separation_min_hz: float = 0.0005
    separation_max_hz: float = 0.022
    separation_step_hz: float = 0.00025
    row_batch_size: int = 4
    candidate_chunk_size: int = 128


def require_cupy():
    try:
        import cupy as cp
    except Exception as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "compute-backend=cupy_batch requires CuPy. Install cupy-cuda12x and CUDA toolkit dependencies first."
        ) from exc
    return cp


def cupy_environment() -> dict:
    cp = require_cupy()
    device_count = int(cp.cuda.runtime.getDeviceCount())
    if device_count < 1:
        raise RuntimeError("compute-backend=cupy_batch requires at least one CUDA device.")
    props = cp.cuda.runtime.getDeviceProperties(0)
    name = props["name"].decode() if isinstance(props["name"], bytes) else str(props["name"])
    free, total = cp.cuda.runtime.memGetInfo()
    return {
        "cupy_version": cp.__version__,
        "cuda_runtime": int(cp.cuda.runtime.runtimeGetVersion()),
        "cuda_device_count": device_count,
        "cuda_device_name": name,
        "cuda_memory_free_mib": int(free // 1024 // 1024),
        "cuda_memory_total_mib": int(total // 1024 // 1024),
    }


def _inclusive_grid(start: float, stop: float, step: float) -> np.ndarray:
    if step <= 0:
        raise ValueError("grid step must be positive")
    count = int(math.floor((stop - start) / step + 0.5)) + 1
    values = start + step * np.arange(max(count, 1), dtype=float)
    return values[(values >= start - 1e-12) & (values <= stop + 1e-12)]


def candidate_pairs(config: CupyBatchConfig) -> np.ndarray:
    if config.center_span_hz <= 0:
        centers = np.asarray([config.center_hz], dtype=float)
    else:
        centers = _inclusive_grid(
            config.center_hz - config.center_span_hz,
            config.center_hz + config.center_span_hz,
            config.center_step_hz,
        )
    separations = _inclusive_grid(config.separation_min_hz, config.separation_max_hz, config.separation_step_hz)
    rows = []
    for center in centers:
        for separation in separations:
            left = center - separation / 2.0
            right = center + separation / 2.0
            if left > 0.001 and right < config.fs / 2.0:
                rows.append((left, right))
    if not rows:
        raise ValueError("cupy_batch candidate grid is empty")
    return np.asarray(rows, dtype=float)


def single_frequencies(pairs: np.ndarray) -> np.ndarray:
    values = np.unique(np.round(pairs.ravel(), 12))
    return np.asarray(values, dtype=float)


def pair_condition_table(t: np.ndarray, pairs: np.ndarray) -> np.ndarray:
    tc = t - float(np.mean(t))
    values = np.empty(len(pairs), dtype=float)
    for index, (left, right) in enumerate(pairs):
        columns = [
            np.sin(2.0 * np.pi * left * tc),
            np.cos(2.0 * np.pi * left * tc),
            np.sin(2.0 * np.pi * right * tc),
            np.cos(2.0 * np.pi * right * tc),
            np.ones_like(t),
        ]
        values[index] = design_diagnostics(np.column_stack(columns))["condition_design"]
    return values


def _batched_sse(cp, y_gpu, columns_gpu):
    """Return batched least-squares SSE for columns shaped (P, C, N)."""
    gram = cp.einsum("pcn,pdn->pcd", columns_gpu, columns_gpu)
    gram_inv = cp.linalg.inv(gram)
    rhs = cp.einsum("pcn,bn->bpc", columns_gpu, y_gpu)
    yty = cp.sum(y_gpu * y_gpu, axis=1)
    explained = cp.einsum("bpc,pcd,bpd->bp", rhs, gram_inv, rhs)
    sse = yty[:, None] - explained
    return cp.maximum(sse, 0.0)


def _variable_batched_sse(cp, y_gpu, columns_gpu):
    """Return SSE for per-row columns shaped (B, P, C, N)."""
    gram = cp.einsum("bpcn,bpdn->bpcd", columns_gpu, columns_gpu)
    gram_inv = cp.linalg.inv(gram)
    rhs = cp.einsum("bpcn,bn->bpc", columns_gpu, y_gpu)
    yty = cp.sum(y_gpu * y_gpu, axis=1)
    explained = cp.einsum("bpc,bpcd,bpd->bp", rhs, gram_inv, rhs)
    sse = yty[:, None] - explained
    return cp.maximum(sse, 0.0)
def estimate_two_tone_batch(
    t: np.ndarray,
    observations: np.ndarray,
    config: CupyBatchConfig,
    pairs: np.ndarray | None = None,
    conditions: np.ndarray | None = None,
) -> tuple[list[dict], dict]:
    """Estimate two close tones for a batch of observations.

    The detector uses a batched one-tone-vs-two-tone BIC comparison.  It keeps
    the experiment-D input definition but does not try to mirror the CPU SIC
    control flow.
    """
    cp = require_cupy()
    started = time.perf_counter()
    pairs = candidate_pairs(config) if pairs is None else np.asarray(pairs, dtype=float)
    conditions = pair_condition_table(t, pairs) if conditions is None else np.asarray(conditions, dtype=float)
    singles = single_frequencies(pairs)
    candidate_elapsed = time.perf_counter() - started

    transfer_started = time.perf_counter()
    y_gpu = cp.asarray(np.asarray(observations, dtype=np.float64))
    t_gpu = cp.asarray(np.asarray(t, dtype=np.float64))
    tc_gpu = t_gpu - cp.mean(t_gpu)
    cp.cuda.Stream.null.synchronize()
    transfer_elapsed = time.perf_counter() - transfer_started

    pair_started = time.perf_counter()
    pair_gpu = cp.asarray(pairs)
    left_angle = 2.0 * cp.pi * pair_gpu[:, 0:1] * tc_gpu[None, :]
    right_angle = 2.0 * cp.pi * pair_gpu[:, 1:2] * tc_gpu[None, :]
    pair_columns = cp.stack(
        [
            cp.sin(left_angle),
            cp.cos(left_angle),
            cp.sin(right_angle),
            cp.cos(right_angle),
            cp.ones_like(left_angle),
        ],
        axis=1,
    )
    pair_sse = _batched_sse(cp, y_gpu, pair_columns)
    pair_bic = y_gpu.shape[1] * cp.log(cp.maximum(pair_sse / y_gpu.shape[1], 1e-300)) + 7.0 * math.log(y_gpu.shape[1])
    best_pair_index_gpu = cp.argmin(pair_bic, axis=1)
    best_pair_bic_gpu = pair_bic[cp.arange(y_gpu.shape[0]), best_pair_index_gpu]
    cp.cuda.Stream.null.synchronize()
    pair_elapsed = time.perf_counter() - pair_started

    single_started = time.perf_counter()
    single_gpu = cp.asarray(singles)
    single_angle = 2.0 * cp.pi * single_gpu[:, None] * tc_gpu[None, :]
    single_columns = cp.stack(
        [cp.sin(single_angle), cp.cos(single_angle), cp.ones_like(single_angle)],
        axis=1,
    )
    single_sse = _batched_sse(cp, y_gpu, single_columns)
    single_bic = y_gpu.shape[1] * cp.log(cp.maximum(single_sse / y_gpu.shape[1], 1e-300)) + 4.0 * math.log(y_gpu.shape[1])
    best_single_index_gpu = cp.argmin(single_bic, axis=1)
    best_single_bic_gpu = single_bic[cp.arange(y_gpu.shape[0]), best_single_index_gpu]
    cp.cuda.Stream.null.synchronize()
    single_elapsed = time.perf_counter() - single_started

    gather_started = time.perf_counter()
    best_pair_index = cp.asnumpy(best_pair_index_gpu).astype(int)
    best_single_index = cp.asnumpy(best_single_index_gpu).astype(int)
    best_pair_bic = cp.asnumpy(best_pair_bic_gpu)
    best_single_bic = cp.asnumpy(best_single_bic_gpu)
    cp.cuda.Stream.null.synchronize()
    gather_elapsed = time.perf_counter() - gather_started

    rows: list[dict] = []
    for row_index, pair_index in enumerate(best_pair_index):
        improvement = float(best_single_bic[row_index] - best_pair_bic[row_index])
        condition = float(conditions[pair_index])
        accepted = bool(improvement >= config.bic_delta and condition <= 1e6)
        estimated = pairs[pair_index] if accepted else np.asarray([singles[best_single_index[row_index]]])
        rows.append(
            {
                "estimated_k": int(2 if accepted else 1),
                "estimated_frequencies_hz": np.asarray(estimated, dtype=float),
                "bic_improvement": improvement,
                "candidate_origin": "cupy_batch_pair_grid",
                "condition_design": condition,
                "ill_conditioned": bool(condition > 1e6),
                "cupy_best_pair_index": int(pair_index),
                "cupy_best_pair_bic": float(best_pair_bic[row_index]),
                "cupy_best_single_bic": float(best_single_bic[row_index]),
            }
        )
    timings = {
        "cupy_candidate_seconds": candidate_elapsed,
        "cupy_transfer_seconds": transfer_elapsed,
        "cupy_pair_seconds": pair_elapsed,
        "cupy_single_seconds": single_elapsed,
        "cupy_gather_seconds": gather_elapsed,
        "cupy_total_seconds": time.perf_counter() - started,
        "cupy_batch_size": int(len(observations)),
        "cupy_pair_candidates": int(len(pairs)),
        "cupy_single_candidates": int(len(singles)),
    }
    return rows, timings


def _coarse_fft_centers(cp, y_gpu, fs: float, f_min_hz: float, f_max_hz: float):
    demeaned = y_gpu - cp.mean(y_gpu, axis=1, keepdims=True)
    spectrum = cp.abs(cp.fft.rfft(demeaned, axis=1)) ** 2
    freqs = cp.fft.rfftfreq(y_gpu.shape[1], d=1.0 / fs)
    mask = (freqs >= f_min_hz) & (freqs <= f_max_hz)
    if int(cp.count_nonzero(mask).get()) < 1:
        raise ValueError("cupy_full_auto coarse FFT search range is empty")
    search_freqs = freqs[mask]
    search_spectrum = spectrum[:, mask]
    peak_indices = cp.argmax(search_spectrum, axis=1)
    return search_freqs[peak_indices]


def estimate_two_tone_full_auto_batch(
    t: np.ndarray,
    observations: np.ndarray,
    config: CupyFullAutoConfig,
) -> tuple[list[dict], dict]:
    """Estimate close two-tone frequencies without a supplied center.

    The detector first finds a coarse center from each observation's FFT, then
    evaluates a local center/separation grid around that center on the GPU.
    """
    cp = require_cupy()
    started = time.perf_counter()
    if config.row_batch_size < 1 or config.candidate_chunk_size < 1:
        raise ValueError("row_batch_size and candidate_chunk_size must be positive")

    transfer_started = time.perf_counter()
    y_gpu = cp.asarray(np.asarray(observations, dtype=np.float64))
    t_gpu = cp.asarray(np.asarray(t, dtype=np.float64))
    tc_gpu = t_gpu - cp.mean(t_gpu)
    cp.cuda.Stream.null.synchronize()
    transfer_elapsed = time.perf_counter() - transfer_started

    coarse_started = time.perf_counter()
    coarse_centers_gpu = _coarse_fft_centers(cp, y_gpu, config.fs, config.f_min_hz, config.f_max_hz)
    cp.cuda.Stream.null.synchronize()
    coarse_elapsed = time.perf_counter() - coarse_started

    offset_values = _inclusive_grid(-config.local_center_span_hz, config.local_center_span_hz, config.local_center_step_hz)
    separation_values = _inclusive_grid(config.separation_min_hz, config.separation_max_hz, config.separation_step_hz)
    offsets_gpu = cp.asarray(offset_values)
    separations_gpu = cp.asarray(separation_values)
    candidate_count = int(len(offset_values) * len(separation_values))
    single_count = int(len(offset_values))

    pair_started = time.perf_counter()
    best_pair_bic = cp.full(y_gpu.shape[0], cp.inf, dtype=cp.float64)
    best_pair_left = cp.full(y_gpu.shape[0], cp.nan, dtype=cp.float64)
    best_pair_right = cp.full(y_gpu.shape[0], cp.nan, dtype=cp.float64)
    best_pair_index = cp.full(y_gpu.shape[0], -1, dtype=cp.int64)
    row_batch_size = min(config.row_batch_size, y_gpu.shape[0])
    for row_start in range(0, y_gpu.shape[0], row_batch_size):
        row_stop = min(row_start + row_batch_size, y_gpu.shape[0])
        y_rows = y_gpu[row_start:row_stop]
        coarse_rows = coarse_centers_gpu[row_start:row_stop]
        centers = coarse_rows[:, None] + offsets_gpu[None, :]
        left = centers[:, :, None] - separations_gpu[None, None, :] / 2.0
        right = centers[:, :, None] + separations_gpu[None, None, :] / 2.0
        pair_grid = cp.stack([left.reshape(row_stop - row_start, -1), right.reshape(row_stop - row_start, -1)], axis=2)
        for candidate_start in range(0, candidate_count, config.candidate_chunk_size):
            candidate_stop = min(candidate_start + config.candidate_chunk_size, candidate_count)
            pairs = pair_grid[:, candidate_start:candidate_stop, :]
            valid = (pairs[:, :, 0] > 0.001) & (pairs[:, :, 1] < config.fs / 2.0)
            left_angle = 2.0 * cp.pi * pairs[:, :, 0, None] * tc_gpu[None, None, :]
            right_angle = 2.0 * cp.pi * pairs[:, :, 1, None] * tc_gpu[None, None, :]
            columns = cp.stack(
                [
                    cp.sin(left_angle),
                    cp.cos(left_angle),
                    cp.sin(right_angle),
                    cp.cos(right_angle),
                    cp.ones_like(left_angle),
                ],
                axis=2,
            )
            sse = _variable_batched_sse(cp, y_rows, columns)
            bic = y_gpu.shape[1] * cp.log(cp.maximum(sse / y_gpu.shape[1], 1e-300)) + 7.0 * math.log(y_gpu.shape[1])
            bic = cp.where(valid, bic, cp.inf)
            local_indices = cp.argmin(bic, axis=1)
            local_bic = bic[cp.arange(row_stop - row_start), local_indices]
            improve = local_bic < best_pair_bic[row_start:row_stop]
            global_indices = candidate_start + local_indices
            best_pairs = pairs[cp.arange(row_stop - row_start), local_indices, :]
            best_pair_bic[row_start:row_stop] = cp.where(improve, local_bic, best_pair_bic[row_start:row_stop])
            best_pair_left[row_start:row_stop] = cp.where(improve, best_pairs[:, 0], best_pair_left[row_start:row_stop])
            best_pair_right[row_start:row_stop] = cp.where(improve, best_pairs[:, 1], best_pair_right[row_start:row_stop])
            best_pair_index[row_start:row_stop] = cp.where(improve, global_indices, best_pair_index[row_start:row_stop])
    cp.cuda.Stream.null.synchronize()
    pair_elapsed = time.perf_counter() - pair_started

    single_started = time.perf_counter()
    best_single_bic = cp.full(y_gpu.shape[0], cp.inf, dtype=cp.float64)
    best_single_freq = cp.full(y_gpu.shape[0], cp.nan, dtype=cp.float64)
    best_single_index = cp.full(y_gpu.shape[0], -1, dtype=cp.int64)
    for row_start in range(0, y_gpu.shape[0], row_batch_size):
        row_stop = min(row_start + row_batch_size, y_gpu.shape[0])
        y_rows = y_gpu[row_start:row_stop]
        coarse_rows = coarse_centers_gpu[row_start:row_stop]
        singles = coarse_rows[:, None] + offsets_gpu[None, :]
        for candidate_start in range(0, single_count, config.candidate_chunk_size):
            candidate_stop = min(candidate_start + config.candidate_chunk_size, single_count)
            freqs = singles[:, candidate_start:candidate_stop]
            valid = (freqs > 0.001) & (freqs < config.fs / 2.0)
            angle = 2.0 * cp.pi * freqs[:, :, None] * tc_gpu[None, None, :]
            columns = cp.stack([cp.sin(angle), cp.cos(angle), cp.ones_like(angle)], axis=2)
            sse = _variable_batched_sse(cp, y_rows, columns)
            bic = y_gpu.shape[1] * cp.log(cp.maximum(sse / y_gpu.shape[1], 1e-300)) + 4.0 * math.log(y_gpu.shape[1])
            bic = cp.where(valid, bic, cp.inf)
            local_indices = cp.argmin(bic, axis=1)
            local_bic = bic[cp.arange(row_stop - row_start), local_indices]
            improve = local_bic < best_single_bic[row_start:row_stop]
            global_indices = candidate_start + local_indices
            best_freqs = freqs[cp.arange(row_stop - row_start), local_indices]
            best_single_bic[row_start:row_stop] = cp.where(improve, local_bic, best_single_bic[row_start:row_stop])
            best_single_freq[row_start:row_stop] = cp.where(improve, best_freqs, best_single_freq[row_start:row_stop])
            best_single_index[row_start:row_stop] = cp.where(improve, global_indices, best_single_index[row_start:row_stop])
    cp.cuda.Stream.null.synchronize()
    single_elapsed = time.perf_counter() - single_started

    gather_started = time.perf_counter()
    coarse_centers = cp.asnumpy(coarse_centers_gpu)
    pair_left = cp.asnumpy(best_pair_left)
    pair_right = cp.asnumpy(best_pair_right)
    pair_bic = cp.asnumpy(best_pair_bic)
    pair_index = cp.asnumpy(best_pair_index).astype(int)
    single_freq = cp.asnumpy(best_single_freq)
    single_bic = cp.asnumpy(best_single_bic)
    single_index = cp.asnumpy(best_single_index).astype(int)
    cp.cuda.Stream.null.synchronize()
    gather_elapsed = time.perf_counter() - gather_started

    condition_started = time.perf_counter()
    rows: list[dict] = []
    tc = t - float(np.mean(t))
    for row_index in range(len(observations)):
        improvement = float(single_bic[row_index] - pair_bic[row_index])
        estimated_pair = np.asarray([pair_left[row_index], pair_right[row_index]], dtype=float)
        if np.all(np.isfinite(estimated_pair)):
            columns = [
                np.sin(2.0 * np.pi * estimated_pair[0] * tc),
                np.cos(2.0 * np.pi * estimated_pair[0] * tc),
                np.sin(2.0 * np.pi * estimated_pair[1] * tc),
                np.cos(2.0 * np.pi * estimated_pair[1] * tc),
                np.ones_like(t),
            ]
            condition = float(design_diagnostics(np.column_stack(columns))["condition_design"])
        else:
            condition = float("inf")
        accepted = bool(improvement >= config.bic_delta and condition <= 1e6)
        estimated = estimated_pair if accepted else np.asarray([single_freq[row_index]], dtype=float)
        rows.append(
            {
                "estimated_k": int(2 if accepted else 1),
                "estimated_frequencies_hz": np.asarray(np.sort(estimated), dtype=float),
                "bic_improvement": improvement,
                "candidate_origin": "cupy_full_auto_fft_local_grid",
                "condition_design": condition,
                "ill_conditioned": bool(condition > 1e6),
                "cupy_best_pair_index": int(pair_index[row_index]),
                "cupy_best_pair_bic": float(pair_bic[row_index]),
                "cupy_best_single_bic": float(single_bic[row_index]),
                "cupy_best_single_index": int(single_index[row_index]),
                "cupy_coarse_center_hz": float(coarse_centers[row_index]),
            }
        )
    condition_elapsed = time.perf_counter() - condition_started
    timings = {
        "cupy_candidate_seconds": 0.0,
        "cupy_transfer_seconds": transfer_elapsed,
        "cupy_coarse_fft_seconds": coarse_elapsed,
        "cupy_pair_seconds": pair_elapsed,
        "cupy_single_seconds": single_elapsed,
        "cupy_gather_seconds": gather_elapsed,
        "cupy_condition_seconds": condition_elapsed,
        "cupy_total_seconds": time.perf_counter() - started,
        "cupy_batch_size": int(len(observations)),
        "cupy_pair_candidates": candidate_count,
        "cupy_single_candidates": single_count,
        "cupy_row_batch_size": int(config.row_batch_size),
        "cupy_candidate_chunk_size": int(config.candidate_chunk_size),
    }
    return rows, timings
