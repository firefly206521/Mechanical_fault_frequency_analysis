"""Adaptive CuPy orchestration helpers for Q3 experiment D."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np


Task = tuple[float, int, float, int]
Cell = tuple[float, int, float]


@dataclass(frozen=True)
class AdaptivePolicy:
    group_id: str
    snr_weak_db: float
    amplitude_ratio_value: int
    separation_hz: float
    center_hz: float
    center_span_hz: float
    source: str
    pilot_rows: int
    pilot_center_min_hz: float
    pilot_center_max_hz: float
    pilot_center_deviation_max_hz: float
    uses_true_center: bool = False


def task_cell(task: Task) -> Cell:
    snr_db, ratio, separation, _ = task
    return (float(snr_db), int(ratio), float(separation))


def group_id(cell: Cell) -> str:
    snr_db, ratio, separation = cell
    return f"snr={snr_db:g}|ratio=1:{ratio}|sep={separation:.12g}"


def group_tasks(tasks: Iterable[Task]) -> dict[Cell, list[Task]]:
    groups: dict[Cell, list[Task]] = defaultdict(list)
    for task in tasks:
        groups[task_cell(task)].append(task)
    return {cell: sorted(rows, key=lambda item: item[3]) for cell, rows in groups.items()}


def select_pilot_tasks(tasks: list[Task], runs_per_cell: int) -> set[Task]:
    if runs_per_cell < 1:
        raise ValueError("adaptive pilot runs per cell must be positive")
    selected: set[Task] = set()
    for rows in group_tasks(tasks).values():
        count = min(runs_per_cell, len(rows))
        if count <= 0:
            continue
        indices = np.linspace(0, len(rows) - 1, count)
        for index in np.unique(np.rint(indices).astype(int)):
            selected.add(rows[int(index)])
    return selected


def select_audit_tasks(tasks: list[Task], audit_rate: float) -> set[Task]:
    if audit_rate <= 0:
        return set()
    if audit_rate > 1:
        raise ValueError("adaptive audit rate must be in [0, 1]")
    selected: set[Task] = set()
    for rows in group_tasks(tasks).values():
        count = max(1, int(math.ceil(len(rows) * audit_rate)))
        indices = np.linspace(0, len(rows) - 1, count)
        for index in np.unique(np.rint(indices).astype(int)):
            selected.add(rows[int(index)])
    return selected


def parse_frequency_text(text: str) -> np.ndarray:
    if text is None or str(text).strip() == "":
        return np.asarray([], dtype=float)
    return np.asarray([float(item) for item in str(text).split(";") if item.strip()], dtype=float)


def learned_center_from_row(row: dict) -> tuple[float, str]:
    estimated = parse_frequency_text(str(row.get("estimated_frequencies_hz", "")))
    if int(float(row.get("estimated_k", 0))) >= 2 and len(estimated) >= 2:
        return float(np.mean(np.sort(estimated)[:2])), "pilot_dual_frequency"
    coarse = row.get("cupy_coarse_center_hz", "")
    if coarse not in ("", None):
        value = float(coarse)
        if math.isfinite(value):
            return value, "pilot_coarse_fallback"
    return float("nan"), "unusable"


def build_policy_rows(
    pilot_rows: list[dict],
    min_span_hz: float,
    margin_hz: float,
    max_span_hz: float,
) -> tuple[list[dict], dict[Cell, AdaptivePolicy]]:
    if min_span_hz < 0 or margin_hz < 0 or max_span_hz < min_span_hz:
        raise ValueError("invalid adaptive center span settings")
    by_cell: dict[Cell, list[tuple[float, str]]] = defaultdict(list)
    for row in pilot_rows:
        cell = (
            float(row["snr_weak_db"]),
            int(float(row["amplitude_ratio_value"])),
            float(row["separation_hz"]),
        )
        center, source = learned_center_from_row(row)
        if math.isfinite(center):
            by_cell[cell].append((center, source))

    policies: dict[Cell, AdaptivePolicy] = {}
    policy_rows: list[dict] = []
    for cell, values in sorted(by_cell.items()):
        centers = np.asarray([item[0] for item in values], dtype=float)
        center_hat = float(np.median(centers))
        max_deviation = float(np.max(np.abs(centers - center_hat))) if len(centers) else float("nan")
        span = min(max(max_deviation + margin_hz, min_span_hz), max_span_hz)
        sources = {item[1] for item in values}
        source = "pilot_dual_frequency" if "pilot_dual_frequency" in sources else "pilot_coarse_fallback"
        snr_db, ratio, separation = cell
        policy = AdaptivePolicy(
            group_id=group_id(cell),
            snr_weak_db=snr_db,
            amplitude_ratio_value=ratio,
            separation_hz=separation,
            center_hz=center_hat,
            center_span_hz=float(span),
            source=source,
            pilot_rows=len(values),
            pilot_center_min_hz=float(np.min(centers)),
            pilot_center_max_hz=float(np.max(centers)),
            pilot_center_deviation_max_hz=max_deviation,
        )
        policies[cell] = policy
        policy_rows.append(
            {
                "adaptive_group_id": policy.group_id,
                "snr_weak_db": policy.snr_weak_db,
                "amplitude_ratio_value": policy.amplitude_ratio_value,
                "separation_hz": policy.separation_hz,
                "adaptive_policy_center_hz": policy.center_hz,
                "adaptive_policy_span_hz": policy.center_span_hz,
                "adaptive_policy_source": policy.source,
                "pilot_rows": policy.pilot_rows,
                "pilot_center_min_hz": policy.pilot_center_min_hz,
                "pilot_center_max_hz": policy.pilot_center_max_hz,
                "pilot_center_deviation_max_hz": policy.pilot_center_deviation_max_hz,
                "uses_true_center": policy.uses_true_center,
            }
        )
    return policy_rows, policies


def row_task_key(row: dict) -> Task:
    return (
        float(row["snr_weak_db"]),
        int(float(row["amplitude_ratio_value"])),
        float(row["separation_hz"]),
        int(row["replicate"]),
    )


def max_frequency_difference(row_a: dict, row_b: dict) -> float:
    freq_a = list(np.sort(parse_frequency_text(str(row_a.get("estimated_frequencies_hz", "")))))
    freq_b = np.sort(parse_frequency_text(str(row_b.get("estimated_frequencies_hz", ""))))
    if len(freq_a) != len(freq_b):
        return float("nan")
    errors = []
    for value in freq_b:
        index = int(np.argmin(np.abs(np.asarray(freq_a) - value)))
        errors.append(abs(freq_a.pop(index) - value))
    return float(max(errors)) if errors else 0.0


def audit_mismatch(fast_row: dict, audit_row: dict, frequency_tolerance_hz: float) -> tuple[bool, str, float]:
    reasons = []
    if int(float(fast_row["estimated_k"])) != int(float(audit_row["estimated_k"])):
        reasons.append("estimated_k")
    if str(fast_row["success"]).lower() != str(audit_row["success"]).lower():
        reasons.append("success")
    if str(fast_row["ill_conditioned"]).lower() != str(audit_row["ill_conditioned"]).lower():
        reasons.append("ill_conditioned")
    frequency_delta = max_frequency_difference(fast_row, audit_row)
    if math.isfinite(frequency_delta) and frequency_delta > frequency_tolerance_hz:
        reasons.append("frequency")
    elif not math.isfinite(frequency_delta):
        reasons.append("frequency_count")
    return bool(reasons), ";".join(reasons), frequency_delta
