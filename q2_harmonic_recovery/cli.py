"""Command-line workflow for Q2 harmonic recovery."""

from __future__ import annotations

import argparse
import csv
import math
import time
from pathlib import Path

import numpy as np

from .core import (
    bootstrap_parameters,
    joint_segment_fit,
    linear_detrend,
    load_single_source,
    model_applicability,
    refine_frequency,
    segment_length_sensitivity,
    simulation_validation,
    spectrum,
    ssa_recovery_comparison,
    targeted_filter_comparison,
)
from .outputs import convert_svg_plots_to_png, write_csv, write_plots, write_report


SEED = 20260619


def locate_data(workspace: Path, explicit: Path | None) -> Path:
    candidates = [
        explicit,
        workspace / "data.xlsx",
        workspace.parent / "A题：机械设备故障检测" / "data.xlsx",
    ]
    for path in candidates:
        if path is not None and path.exists():
            return path.resolve()
    raise FileNotFoundError("Cannot locate data.xlsx; pass --data explicitly.")


def load_q1_frequency(workspace: Path, fallback: float = 2.0000015345118274) -> float:
    path = workspace / "q1_glrt_results" / "q1_glrt_result.csv"
    if not path.exists():
        return fallback
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    return float(row["refined_frequency_hz"])


def parse_args():
    parser = argparse.ArgumentParser(description="Run Q2 harmonic waveform recovery.")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bootstrap-runs", type=int, default=10000)
    parser.add_argument("--simulation-runs", type=int, default=200)
    return parser.parse_args()


def main():
    args = parse_args()
    package_dir = Path(__file__).resolve().parent
    workspace = package_dir.parent
    data_path = locate_data(workspace, args.data)
    output_dir = (args.output_dir or workspace / "q2_harmonic_recovery_results").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    t, x, fs = load_single_source(data_path)
    y, trend = linear_detrend(t, x)
    q1_frequency = load_q1_frequency(workspace)
    fit = refine_frequency(t, y, q1_frequency, half_width=0.01)
    signal_power = float(np.mean((fit["fit"] - fit["offset"]) ** 2))
    noise_power = float(np.mean(fit["residual"] ** 2))
    diagnostics, bands = model_applicability(t, x, y, fit, fs)
    diag_map = {(r["source"], r["metric"]): r["value"] for r in diagnostics}

    bootstrap_started = time.perf_counter()
    bootstrap_rows, _ = bootstrap_parameters(t, fit, args.bootstrap_runs, SEED)
    bootstrap_seconds = time.perf_counter() - bootstrap_started

    segment_detail_rows, segment_sensitivity_rows = segment_length_sensitivity(t, y, fit["frequency_hz"], fs)
    joint_rows = [row.copy() for row in segment_detail_rows if row["segment_seconds"] == 50.0]
    for row in joint_rows:
        row.pop("segment_seconds", None)
    model_50 = next(row for row in segment_sensitivity_rows if row["segment_seconds"] == 50.0)
    model_comparison = [
        {"model": "common frequency", "parameters": 25, "sse": model_50["common_frequency_sse"], "bic": model_50["common_frequency_bic"]},
        {"model": "independent frequencies", "parameters": 32, "sse": model_50["independent_frequencies_sse"], "bic": model_50["independent_frequencies_bic"]},
    ]
    filter_rows, filtered, _ = targeted_filter_comparison(t, y, fit, fs)
    ssa_rows, ssa_best, ssa_best_window = ssa_recovery_comparison(t, y, fit, fs)
    # Use the same 40,001 samples as the real record so simulation accuracy is
    # directly comparable with the full-data recovery task.
    simulation_rows = simulation_validation(
        fs,
        len(t),
        fit["amplitude"],
        SEED,
        args.simulation_runs,
        f_true=fit["frequency_hz"],
    )

    global_rows = [{
        "data_path": str(data_path),
        "sample_count": len(t),
        "sampling_rate_hz": fs,
        "duration_s": float(t[-1] - t[0]),
        "q1_input_frequency_hz": q1_frequency,
        "frequency_hz": fit["frequency_hz"],
        "amplitude": fit["amplitude"],
        "phase_origin_rad": fit["phase_origin_rad"],
        "offset_after_detrend": fit["offset"],
        "residual_std": float(np.std(fit["residual"])),
        "residual_rmse": fit["rmse"],
        "explained_variance": fit["explained_variance"],
        "estimated_snr_db": 10.0 * math.log10(signal_power / noise_power),
        "target_peak_suppression_db": diag_map[("spectrum", "target_peak_suppression_db")],
        "mckd_branch_triggered": bool(diag_map[("decision", "trigger_mckd_branch")]),
        "linear_trend_slope": float(trend[0]),
        "linear_trend_intercept": float(trend[1]),
        "bootstrap_runs": args.bootstrap_runs,
        "bootstrap_runtime_seconds": bootstrap_seconds,
        "simulation_runs_per_snr": args.simulation_runs,
        "random_seed": SEED,
    }]

    write_csv(output_dir / "q2_global_parameters.csv", global_rows)
    write_csv(output_dir / "q2_applicability_diagnostics.csv", diagnostics)
    write_csv(output_dir / "q2_band_power.csv", bands)
    write_csv(output_dir / "q2_bootstrap_ci.csv", bootstrap_rows)
    write_csv(output_dir / "q2_joint_segment_fit.csv", joint_rows)
    write_csv(output_dir / "q2_joint_model_comparison.csv", model_comparison)
    write_csv(output_dir / "q2_joint_segment_fit_sensitivity.csv", segment_detail_rows)
    write_csv(output_dir / "q2_segment_length_sensitivity.csv", segment_sensitivity_rows)
    write_csv(output_dir / "q2_targeted_filter_comparison.csv", filter_rows)
    write_csv(output_dir / "q2_ssa_comparison.csv", ssa_rows)
    write_csv(output_dir / "q2_simulation_validation.csv", simulation_rows)
    write_plots(
        output_dir, t, y, fit, filtered, joint_rows, simulation_rows, fs,
        ssa_best=ssa_best, ssa_best_window=ssa_best_window,
        segment_sensitivity_rows=segment_sensitivity_rows,
    )
    png_outputs = convert_svg_plots_to_png(output_dir, remove_svg=True)
    write_report(output_dir / "q2_report.md", {
        "global": global_rows[0],
        "bootstrap": bootstrap_rows,
        "bootstrap_runs": args.bootstrap_runs,
        "seed": SEED,
        "diagnostics": diagnostics,
        "model_comparison": model_comparison,
        "filter_comparison": filter_rows,
        "ssa_comparison": ssa_rows,
        "ssa_best_window": ssa_best_window,
        "segment_sensitivity": segment_sensitivity_rows,
        "simulation": simulation_rows,
    })
    total_seconds = time.perf_counter() - started
    (output_dir / "q2_runtime.txt").write_text(
        f"bootstrap_runs={args.bootstrap_runs}\nbootstrap_seconds={bootstrap_seconds:.6f}\n"
        f"simulation_runs_per_snr={args.simulation_runs}\nsimulation_sample_count={len(t)}\n"
        f"ssa_best_window_points={ssa_best_window}\ntotal_seconds={total_seconds:.6f}\n",
        encoding="utf-8",
    )
    print(f"Q2 output: {output_dir}")
    print(f"frequency={fit['frequency_hz']:.12f} Hz, amplitude={fit['amplitude']:.9f}, phase={fit['phase_origin_rad']:.9f}")
    print(f"bootstrap {args.bootstrap_runs} runs: {bootstrap_seconds:.3f} s; total: {total_seconds:.3f} s")
    print(f"PNG plots rendered: {len(png_outputs)}")


if __name__ == "__main__":
    main()
