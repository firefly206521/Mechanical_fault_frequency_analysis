"""Command-line entry point for the Q1 GLRT workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from q1_glrt.core import (
    analyze_preprocessing_and_noise,
    build_parameter_table,
    run_fft_glrt_simulation,
    run_glrt_q1,
    run_segment_validation,
)
from q1_glrt.outputs import configure_plot_fonts, write_all_outputs
from q1_model_compare import Config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the selected Q1 GLRT model.")
    parser.add_argument("--data", type=Path, default=Path("data.xlsx"))
    parser.add_argument("--output-dir", type=Path, default=Path("q1_glrt_results"))
    parser.add_argument("--glrt-mc", type=int, default=500)
    parser.add_argument("--p-fa", type=float, default=0.05)
    parser.add_argument("--f-min", type=float, default=0.05)
    parser.add_argument("--f-max", type=float, default=49.5)
    parser.add_argument("--sim-mc", type=int, default=200)
    parser.add_argument("--segment-seconds", type=float, default=50.0)
    return parser.parse_args()


def main() -> None:
    configure_plot_fonts()
    args = parse_args()
    cfg = Config(
        data_path=args.data,
        output_dir=args.output_dir,
        f_min=args.f_min,
        f_max=args.f_max,
        p_fa=args.p_fa,
        glrt_mc=args.glrt_mc,
    )
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    result = run_glrt_q1(cfg)
    noise_df = analyze_preprocessing_and_noise(cfg, result)
    parameter_df = build_parameter_table(cfg)
    segment_df = run_segment_validation(cfg, segment_seconds=args.segment_seconds)
    simulation_df = run_fft_glrt_simulation(
        cfg,
        f0=float(result["refined_frequency_hz"]),
        amplitude=float(result["amplitude_for_reference"]),
        fs=float(result["sampling_rate_hz"]),
        n=int(result["sample_count"]),
        sim_mc=args.sim_mc,
    )
    write_all_outputs(cfg, result, noise_df, parameter_df, segment_df, simulation_df)

    print("Q1 GLRT result")
    for key, value in result.items():
        print(f"{key}: {value}")
    print(f"\nWrote outputs to: {cfg.output_dir.resolve()}")


if __name__ == "__main__":
    main()
