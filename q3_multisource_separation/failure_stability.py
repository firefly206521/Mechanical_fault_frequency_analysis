"""Check whether close-frequency failures persist under fresh noise.

This diagnostic fixes signal phases taken from selected Monte Carlo trials and
then changes only the Gaussian noise.  It separates phase-dependent structural
difficulty from an accidental unfavorable noise realization.
"""

from __future__ import annotations

import argparse
import csv
import math
import time
from pathlib import Path

import numpy as np

from . import SEED
from .core import close_pair_resolver, load_multi_source
from .experiments import AMPLITUDE_CASES, EXTREME_CASES, SEPARATIONS, trial_rng, wilson_interval


def _source_phases(experiment_id: int, replicate: int) -> np.ndarray:
    """Recreate the two phases used by an existing deterministic trial."""
    return trial_rng(experiment_id, replicate).uniform(-np.pi, np.pi, 2)


def _scenarios() -> list[dict]:
    identical_id = 4000 + EXTREME_CASES.index("identical_frequency")
    equal_id = 2000 + SEPARATIONS.index(0.0025)
    unequal_id = 2000 + 100 + SEPARATIONS.index(0.003)
    specs = [
        ("identical_failed_seed_19", "identical", 0.0, (0.02, 0.02), _source_phases(identical_id, 19)),
        ("identical_failed_seed_65", "identical", 0.0, (0.02, 0.02), _source_phases(identical_id, 65)),
        ("identical_control_seed_0", "identical", 0.0, (0.02, 0.02), _source_phases(identical_id, 0)),
        ("identical_near_cancel", "identical", 0.0, (0.02, 0.02), np.asarray([0.0, np.pi - 0.03])),
        ("equal_0025_failed_seed_9", "equal", 0.0025, AMPLITUDE_CASES["equal"], _source_phases(equal_id, 9)),
        ("equal_0025_failed_seed_32", "equal", 0.0025, AMPLITUDE_CASES["equal"], _source_phases(equal_id, 32)),
        ("equal_0025_failed_seed_130", "equal", 0.0025, AMPLITUDE_CASES["equal"], _source_phases(equal_id, 130)),
        ("equal_0025_control_seed_0", "equal", 0.0025, AMPLITUDE_CASES["equal"], _source_phases(equal_id, 0)),
        ("unequal_003_failed_seed_6", "unequal", 0.003, AMPLITUDE_CASES["unequal"], _source_phases(unequal_id, 6)),
        ("unequal_003_failed_seed_17", "unequal", 0.003, AMPLITUDE_CASES["unequal"], _source_phases(unequal_id, 17)),
        ("unequal_003_failed_seed_26", "unequal", 0.003, AMPLITUDE_CASES["unequal"], _source_phases(unequal_id, 26)),
        ("unequal_003_control_seed_0", "unequal", 0.003, AMPLITUDE_CASES["unequal"], _source_phases(unequal_id, 0)),
    ]
    return [
        {
            "scenario": name,
            "case": case,
            "separation_hz": separation,
            "amplitudes": np.asarray(amplitudes, float),
            "phases": np.asarray(phases, float),
        }
        for name, case, separation, amplitudes, phases in specs
    ]


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(data_path: Path, result_dir: Path, runs: int) -> tuple[list[dict], list[dict]]:
    if runs < 1:
        raise ValueError("--runs must be positive")
    t, _, _ = load_multi_source(data_path)
    with (result_dir / "q3_global_parameters.csv").open(encoding="utf-8-sig", newline="") as handle:
        noise_std = float(next(csv.DictReader(handle))["residual_std"])

    trials: list[dict] = []
    scenarios = _scenarios()
    for scenario_index, scenario in enumerate(scenarios):
        separation = scenario["separation_hz"]
        frequencies = np.asarray([13.5, 13.5]) if separation == 0.0 else np.asarray(
            [13.5 - separation / 2.0, 13.5 + separation / 2.0]
        )
        signal = sum(
            amplitude * np.sin(2.0 * np.pi * frequency * t + phase)
            for amplitude, frequency, phase in zip(scenario["amplitudes"], frequencies, scenario["phases"])
        )
        phase_difference = float(np.angle(np.exp(1j * (scenario["phases"][1] - scenario["phases"][0]))))
        started_group = time.perf_counter()
        for replicate in range(runs):
            rng = np.random.default_rng(np.random.SeedSequence([SEED, 9000, scenario_index, replicate]))
            observed = signal + rng.normal(0.0, noise_std, len(t))
            started = time.perf_counter()
            estimate = close_pair_resolver(t, observed)
            elapsed = time.perf_counter() - started
            estimated = np.sort(np.asarray(estimate["frequencies_hz"], float))
            if separation == 0.0:
                max_error = float("nan")
                success = len(estimated) <= 1
                failure_type = "over_split" if not success else "none"
            else:
                max_error = float(np.max(np.abs(estimated - frequencies))) if len(estimated) == 2 else float("nan")
                success = bool(len(estimated) == 2 and max_error <= separation / 4.0 and not estimate["ill_conditioned"])
                if success:
                    failure_type = "none"
                elif len(estimated) < 2:
                    failure_type = "not_split"
                elif len(estimated) > 2:
                    failure_type = "over_split"
                else:
                    failure_type = "two_but_inaccurate"
            trials.append({
                "scenario": scenario["scenario"],
                "case": scenario["case"],
                "separation_hz": separation,
                "phase_1_rad": float(scenario["phases"][0]),
                "phase_2_rad": float(scenario["phases"][1]),
                "wrapped_phase_difference_rad": phase_difference,
                "noise_replicate": replicate,
                "estimated_k": len(estimated),
                "success": success,
                "failure_type": failure_type,
                "max_frequency_error_hz": max_error,
                "estimated_frequencies_hz": ";".join(f"{value:.10g}" for value in estimated),
                "bic_improvement": estimate.get("bic_improvement", float("nan")),
                "residual_peak_ratio": estimate.get("residual_peak_ratio", float("nan")),
                "candidate_origin": estimate.get("candidate_origin", ""),
                "condition_design": estimate["condition_design"],
                "runtime_seconds": elapsed,
            })
        print(
            f"{scenario['scenario']}: {runs}/{runs}; elapsed={time.perf_counter()-started_group:.1f}s",
            flush=True,
        )

    summary: list[dict] = []
    for scenario in scenarios:
        group = [row for row in trials if row["scenario"] == scenario["scenario"]]
        successes = sum(bool(row["success"]) for row in group)
        failures = len(group) - successes
        low, high = wilson_interval(successes, len(group))
        types = {name: sum(row["failure_type"] == name for row in group) for name in ("over_split", "not_split", "two_but_inaccurate")}
        errors = [float(row["max_frequency_error_hz"]) for row in group if math.isfinite(float(row["max_frequency_error_hz"]))]
        summary.append({
            "scenario": scenario["scenario"],
            "case": scenario["case"],
            "separation_hz": scenario["separation_hz"],
            "wrapped_phase_difference_rad": group[0]["wrapped_phase_difference_rad"],
            "runs": len(group),
            "successes": successes,
            "failures": failures,
            "success_rate": successes / len(group),
            "success_ci95_low": low,
            "success_ci95_high": high,
            "stable_failure": failures / len(group) >= 0.9,
            "over_split_failures": types["over_split"],
            "not_split_failures": types["not_split"],
            "inaccurate_two_source_failures": types["two_but_inaccurate"],
            "median_max_frequency_error_hz": float(np.median(errors)) if errors else float("nan"),
            "mean_runtime_seconds": float(np.mean([row["runtime_seconds"] for row in group])),
        })
    _write_csv(result_dir / "q3_failure_stability_trials.csv", trials)
    _write_csv(result_dir / "q3_failure_stability_summary.csv", summary)
    return trials, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress-test reproducibility of selected Q3 failures.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=50)
    args = parser.parse_args()
    _, summary = run(args.data.resolve(), args.result_dir.resolve(), args.runs)
    print("\nSummary")
    for row in summary:
        print(f"{row['scenario']}: success={100*row['success_rate']:.1f}%, stable_failure={row['stable_failure']}")


if __name__ == "__main__":
    main()
