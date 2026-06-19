"""Command-line entrypoint for Q4 sensor layout optimization."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import Q4Config
from .experiments import SNR_LEVELS, run_experiments
from .outputs import write_csv, write_plots, write_report, write_result_readme, write_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q4 sensor layout robustness optimization")
    parser.add_argument("--output-dir", type=Path, default=Path("q4_sensor_layout_results"))
    parser.add_argument("--runs", type=int, default=200, help="Monte Carlo runs per SNR/layout/scenario")
    parser.add_argument("--false-alarm-runs", type=int, default=500, help="Pure-noise runs per SNR/layout/scenario")
    parser.add_argument("--threshold-mc", type=int, default=500, help="Monte Carlo samples for layout threshold calibration")
    parser.add_argument("--seed", type=int, default=20260619)
    parser.add_argument("--p-fa", type=float, default=0.05)
    parser.add_argument("--lambda-pfa", type=float, default=2.0)
    parser.add_argument("--mu-balance", type=float, default=0.5)
    parser.add_argument("--fs", type=float, default=100.0)
    parser.add_argument("--duration-s", type=float, default=40.0)
    parser.add_argument("--snr-levels", type=float, nargs="*", default=list(SNR_LEVELS))
    parser.add_argument("--scenarios", nargs="*", default=None, help="Optional subset: balanced spatial_noise_skew weak_single_sensor source_shadow")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Q4Config(
        fs=args.fs,
        duration_s=args.duration_s,
        p_fa=args.p_fa,
        threshold_mc=args.threshold_mc,
        lambda_pfa=args.lambda_pfa,
        mu_balance=args.mu_balance,
        random_seed=args.seed,
    )
    output_dir = args.output_dir
    paper_dir = output_dir / "paper"
    raw_dir = output_dir / "raw"
    paper_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    context = run_experiments(
        cfg=cfg,
        runs=args.runs,
        false_alarm_runs=args.false_alarm_runs,
        snr_levels=tuple(args.snr_levels),
        scenario_names=tuple(args.scenarios) if args.scenarios else None,
    )
    write_result_readme(output_dir / "README.md")
    write_csv(paper_dir / "q4_layout_ranking.csv", context["layout_ranking"])
    write_csv(paper_dir / "q4_snr_performance.csv", context["selected_snr_rows"])
    write_csv(paper_dir / "q4_fault_coverage.csv", context["coverage_rows"])
    write_csv(paper_dir / "q4_noise_robustness.csv", context["robustness_rows"])
    write_report(paper_dir / "q4_report.md", context)
    plots = write_plots(paper_dir, context)

    write_csv(raw_dir / "q4_all_layout_snr_summary.csv", context["snr_summary"])
    write_csv(raw_dir / "q4_detection_trials.csv", context["detection_rows"])
    write_csv(raw_dir / "q4_false_alarm_trials.csv", context["false_alarm_rows"])
    write_runtime(raw_dir / "q4_runtime.txt", context)
    print(f"Q4 completed: {output_dir.resolve()}")
    print(f"Paper outputs: {paper_dir.resolve()}")
    print(f"Raw outputs: {raw_dir.resolve()}")
    print(f"Layouts ranked: {len(context['layout_ranking'])}")
    print(f"PNG plots: {len(plots)}")
    print(f"Runtime seconds: {context['runtime_seconds']:.3f}")


if __name__ == "__main__":
    main()
