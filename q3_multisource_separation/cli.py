"""Command-line workflow for Q3 multi-source separation."""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np

from q2_harmonic_recovery.core import linear_detrend, moment_metrics
from q2_harmonic_recovery.outputs import write_csv

from . import SEED
from .core import (
    component_table,
    detect_multitone,
    GLRTConfig,
    load_multi_source,
    multi_harmonic_fit,
    segment_stability,
)
from .experiments import (
    AMPLITUDE_CASES,
    SEPARATIONS,
    SNR_LEVELS,
    empirical_limit,
    run_null_trial,
    run_resolution_trial,
    run_simulation_trial,
    summarize_resolution,
    summarize_simulation,
)
from .outputs import append_csv_rows, read_csv_rows, write_plots, write_report


def locate_data(workspace: Path, explicit: Path | None) -> Path:
    candidates = [explicit, workspace / "data.xlsx", workspace.parent / "A题：机械设备故障检测" / "data.xlsx"]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("Cannot locate data.xlsx; pass --data explicitly.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Q3 multi-source fault separation.")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--simulation-runs", type=int, default=200)
    parser.add_argument("--resolution-runs", type=int, default=200)
    parser.add_argument("--null-runs", type=int, default=500)
    parser.add_argument("--glrt-mc", type=int, default=500)
    parser.add_argument("--max-components", type=int, default=10)
    parser.add_argument("--music-local-grid-step", type=float, default=0.000025)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-simulation", action="store_true")
    parser.add_argument("--skip-resolution", action="store_true")
    parser.add_argument("--skip-null", action="store_true")
    return parser.parse_args()


def _bool(value) -> bool:
    return str(value).lower() == "true"


def _progress(label: str, completed: int, target: int, started: float) -> None:
    elapsed = time.perf_counter() - started
    rate = elapsed / max(completed, 1)
    remaining = rate * max(target - completed, 0)
    print(f"{label}: {completed}/{target}; elapsed={elapsed:.1f}s; remaining≈{remaining:.1f}s", flush=True)


def main() -> None:
    args = parse_args()
    package_dir = Path(__file__).resolve().parent
    workspace = package_dir.parent
    output_dir = (args.output_dir or workspace / "q3_multisource_separation_results").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = locate_data(workspace, args.data)
    started_total = time.perf_counter()

    load_started = time.perf_counter()
    t, raw, fs = load_multi_source(data_path)
    y, trend = linear_detrend(t, raw)
    load_seconds = time.perf_counter() - load_started
    cfg = GLRTConfig(
        f_min=0.05,
        f_max=49.5,
        p_fa=0.05 / args.max_components,
        glrt_mc=args.glrt_mc,
        random_seed=SEED,
    )

    actual_started = time.perf_counter()
    fit, history = detect_multitone(t, y, fs, cfg, max_components=args.max_components)
    components = component_table(fit)
    segments = segment_stability(t, y, fit["frequencies_hz"], 50.0)
    residual_metrics = moment_metrics(fit["residual"])
    residual_rows = [{"metric": key, "value": value} for key, value in residual_metrics.items()]
    residual_rows.extend([
        {"metric": "explained_variance", "value": fit["explained_variance"]},
        {"metric": "condition_design", "value": fit["condition_design"]},
        {"metric": "condition_normal", "value": fit["condition_normal"]},
    ])
    noise_std = float(np.std(fit["residual"]))
    total_signal_power = float(sum(row["amplitude"] ** 2 / 2.0 for row in components))
    global_rows = [{
        "data_path": str(data_path),
        "sample_count": len(t),
        "sampling_rate_hz": fs,
        "duration_s": float(t[-1] - t[0]),
        "estimated_k": len(components),
        "residual_std": noise_std,
        "explained_variance": fit["explained_variance"],
        "total_snr_db": 10.0 * math.log10(total_signal_power / noise_std ** 2),
        "condition_design": fit["condition_design"],
        "condition_normal": fit["condition_normal"],
        "numerical_rank": fit["numerical_rank"],
        "column_count": fit["column_count"],
        "ill_conditioned": fit["ill_conditioned"],
        "random_seed": SEED,
        "p_fa_total": 0.05,
        "p_fa_step": cfg.p_fa,
        "bic_acceptance_delta": 10.0,
        "linear_trend_slope": float(trend[0]),
        "linear_trend_intercept": float(trend[1]),
    }]
    write_csv(output_dir / "q3_global_parameters.csv", global_rows)
    write_csv(output_dir / "q3_detected_components.csv", components)
    write_csv(output_dir / "q3_model_selection.csv", history)
    write_csv(output_dir / "q3_condition_diagnostics.csv", [{key: fit[key] for key in ["condition_design", "condition_normal", "smallest_singular_value", "numerical_rank", "column_count", "ill_conditioned", "warning_conditioned"]}])
    write_csv(output_dir / "q3_segment_stability.csv", segments)
    write_csv(output_dir / "q3_residual_diagnostics.csv", residual_rows)
    actual_analysis_seconds = time.perf_counter() - actual_started

    simulation_path = output_dir / "q3_simulation_trials.csv"
    resolution_path = output_dir / "q3_resolution_trials.csv"
    null_path = output_dir / "q3_null_trials.csv"
    if not args.resume:
        for path in [simulation_path, resolution_path, null_path]:
            if path.exists():
                path.unlink()

    simulation_stage_started = time.perf_counter()
    simulation_rows = read_csv_rows(simulation_path)
    if not args.skip_simulation:
        existing = {(float(row["snr_total_db"]), int(row["replicate"])) for row in simulation_rows}
        for snr in SNR_LEVELS:
            pending = [rep for rep in range(args.simulation_runs) if (snr, rep) not in existing]
            batch = []
            condition_started = time.perf_counter()
            for count, replicate in enumerate(pending, 1):
                batch.append(run_simulation_trial(t, fs, fit, snr, replicate, cfg))
                if len(batch) == 20 or count == len(pending):
                    append_csv_rows(simulation_path, batch)
                    simulation_rows.extend(batch)
                    batch.clear()
                    _progress(f"多源仿真 SNR={snr:g} dB", count, len(pending), condition_started)
    simulation_stage_seconds = time.perf_counter() - simulation_stage_started

    null_stage_started = time.perf_counter()
    null_rows = read_csv_rows(null_path)
    if not args.skip_null:
        existing = {int(row["replicate"]) for row in null_rows}
        pending = [rep for rep in range(args.null_runs) if rep not in existing]
        batch = []
        condition_started = time.perf_counter()
        for count, replicate in enumerate(pending, 1):
            batch.append(run_null_trial(t, fs, noise_std, replicate, cfg))
            if len(batch) == 20 or count == len(pending):
                append_csv_rows(null_path, batch)
                null_rows.extend(batch)
                batch.clear()
                _progress("纯噪声误报实验", count, len(pending), condition_started)
    null_stage_seconds = time.perf_counter() - null_stage_started

    resolution_stage_started = time.perf_counter()
    resolution_rows = read_csv_rows(resolution_path)
    if not args.skip_resolution:
        existing = {(row["amplitude_case"], float(row["separation_hz"]), int(row["replicate"])) for row in resolution_rows}
        for case in AMPLITUDE_CASES:
            for separation in SEPARATIONS:
                pending = [rep for rep in range(args.resolution_runs) if (case, separation, rep) not in existing]
                batch = []
                condition_started = time.perf_counter()
                for count, replicate in enumerate(pending, 1):
                    batch.append(run_resolution_trial(t, noise_std, separation, case, replicate, args.music_local_grid_step))
                    if len(batch) == 20 or count == len(pending):
                        append_csv_rows(resolution_path, batch)
                        resolution_rows.extend(batch)
                        batch.clear()
                        _progress(f"近频实验 {case}, Δf={separation:g} Hz", count, len(pending), condition_started)
    resolution_stage_seconds = time.perf_counter() - resolution_stage_started

    simulation_summary = summarize_simulation(simulation_rows)
    resolution_summary = summarize_resolution(resolution_rows)
    write_csv(output_dir / "q3_simulation_validation.csv", simulation_summary)
    write_csv(output_dir / "q3_resolution_limit.csv", resolution_summary)
    write_csv(output_dir / "q3_music_comparison.csv", [{
        "amplitude_case": row["amplitude_case"],
        "separation_hz": row["separation_hz"],
        "runs": row["runs"],
        "main_success_rate": row["main_success_rate"],
        "music_success_rate": row["music_success_rate"],
        "music_grid_step_hz": args.music_local_grid_step,
    } for row in resolution_summary])

    output_stage_started = time.perf_counter()
    png = write_plots(output_dir, t, y, fit, history, segments, simulation_summary, resolution_summary, fs)
    write_report(output_dir / "q3_report.md", {
        "fit": fit,
        "components": components,
        "simulation_summary": simulation_summary,
        "resolution_summary": resolution_summary,
        "null_rows": null_rows,
    })
    output_stage_seconds = time.perf_counter() - output_stage_started

    total_seconds = time.perf_counter() - started_total
    false_alarm = float(np.mean([_bool(row["false_alarm"]) for row in null_rows])) if null_rows else float("nan")
    mean_simulation_trial = float(np.mean([float(row["runtime_seconds"]) for row in simulation_rows])) if simulation_rows else float("nan")
    mean_main_resolution = float(np.mean([float(row["main_runtime_seconds"]) for row in resolution_rows])) if resolution_rows else float("nan")
    mean_music_resolution = float(np.mean([float(row["music_runtime_seconds"]) for row in resolution_rows])) if resolution_rows else float("nan")
    mean_null_trial = float(np.mean([float(row["runtime_seconds"]) for row in null_rows])) if null_rows else float("nan")
    estimated_full = actual_analysis_seconds + output_stage_seconds
    if np.isfinite(mean_simulation_trial):
        estimated_full += mean_simulation_trial * len(SNR_LEVELS) * args.simulation_runs
    if np.isfinite(mean_main_resolution) and np.isfinite(mean_music_resolution):
        estimated_full += (
            (mean_main_resolution + mean_music_resolution)
            * len(AMPLITUDE_CASES)
            * len(SEPARATIONS)
            * args.resolution_runs
        )
    if np.isfinite(mean_null_trial):
        estimated_full += mean_null_trial * args.null_runs
    runtime_lines = [
        f"simulation_target_runs={args.simulation_runs}",
        f"resolution_target_runs={args.resolution_runs}",
        f"null_target_runs={args.null_runs}",
        f"simulation_completed_rows={len(simulation_rows)}",
        f"resolution_completed_rows={len(resolution_rows)}",
        f"null_completed_rows={len(null_rows)}",
        f"empirical_false_alarm_rate={false_alarm}",
        f"equal_amplitude_empirical_limit_hz={empirical_limit(resolution_summary, 'equal')}",
        f"unequal_amplitude_empirical_limit_hz={empirical_limit(resolution_summary, 'unequal')}",
        f"load_seconds={load_seconds:.6f}",
        f"actual_analysis_seconds={actual_analysis_seconds:.6f}",
        f"simulation_stage_seconds={simulation_stage_seconds:.6f}",
        f"null_stage_seconds={null_stage_seconds:.6f}",
        f"resolution_stage_seconds={resolution_stage_seconds:.6f}",
        f"output_stage_seconds={output_stage_seconds:.6f}",
        f"mean_simulation_trial_seconds={mean_simulation_trial}",
        f"mean_main_resolution_trial_seconds={mean_main_resolution}",
        f"mean_music_resolution_trial_seconds={mean_music_resolution}",
        f"mean_null_trial_seconds={mean_null_trial}",
        f"estimated_full_seconds={estimated_full}",
        f"total_seconds={total_seconds:.6f}",
        f"png_count={len(png)}",
    ]
    (output_dir / "q3_runtime.txt").write_text("\n".join(runtime_lines) + "\n", encoding="utf-8")
    print(f"Q3 output: {output_dir}")
    print(f"Detected K={len(components)}: {[round(row['frequency_hz'], 9) for row in components]}")
    print(f"Total runtime: {total_seconds:.1f} s; PNG plots: {len(png)}")


if __name__ == "__main__":
    main()
