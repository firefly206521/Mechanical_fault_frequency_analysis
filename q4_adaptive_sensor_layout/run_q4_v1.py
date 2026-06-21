"""Command-line entrypoint for Q4 V1 adaptive sensor layout."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import Q4V1Config
from .experiments import PROFILE_DEFAULTS, SNR_LEVELS, run_experiments
from .outputs import write_all_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Q4 V1 adaptive sensor layout optimization")
    parser.add_argument("--output-dir", type=Path, default=Path("q4_sensor_layout_v1_results"))
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="smoke")
    parser.add_argument("--seed", type=int, default=20260620)
    parser.add_argument("--grid-size", type=int, default=None)
    parser.add_argument("--top-layouts", type=int, default=None)
    parser.add_argument("--runs", type=int, default=None)
    parser.add_argument("--false-alarm-runs", type=int, default=None)
    parser.add_argument("--threshold-mc", type=int, default=None)
    parser.add_argument("--duration-s", type=float, default=None)
    parser.add_argument("--p-fa", type=float, default=0.05)
    parser.add_argument("--fs", type=float, default=100.0)
    parser.add_argument("--snr-levels", type=float, nargs="*", default=list(SNR_LEVELS))
    parser.add_argument("--weight-mean-lambda", type=float, default=0.10)
    parser.add_argument("--weight-trace-info", type=float, default=0.002)
    parser.add_argument("--weight-min-eigen", type=float, default=0.002)
    parser.add_argument("--weight-redundancy", type=float, default=-0.03)
    parser.add_argument("--response-gain-jitter", type=float, default=0.0)
    parser.add_argument("--response-phase-jitter", type=float, default=0.0)
    parser.add_argument("--noise-correlation", type=float, default=0.0)
    parser.add_argument("--response-jitter-mode", choices=("sensor", "element"), default="sensor")
    parser.add_argument("--validation-weight-pd", type=float, default=0.45)
    parser.add_argument("--validation-weight-low-snr", type=float, default=0.35)
    parser.add_argument("--validation-weight-min-pd", type=float, default=0.20)
    parser.add_argument("--validation-weight-fa-excess", type=float, default=-2.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    defaults = PROFILE_DEFAULTS[args.profile]
    grid_size = args.grid_size if args.grid_size is not None else int(defaults["grid_size"])
    top_layouts = args.top_layouts if args.top_layouts is not None else int(defaults["top_layouts"])
    runs = args.runs if args.runs is not None else int(defaults["runs"])
    false_alarm_runs = args.false_alarm_runs if args.false_alarm_runs is not None else int(defaults["false_alarm_runs"])
    threshold_mc = args.threshold_mc if args.threshold_mc is not None else int(defaults["threshold_mc"])
    duration_s = args.duration_s if args.duration_s is not None else float(defaults["duration_s"])
    if grid_size < 6:
        raise ValueError("--grid-size must be at least 6")
    if top_layouts <= 0:
        raise ValueError("--top-layouts must be positive")
    if runs <= 0:
        raise ValueError("--runs must be positive")
    if false_alarm_runs < 0:
        raise ValueError("--false-alarm-runs must be non-negative")
    if threshold_mc <= 0:
        raise ValueError("--threshold-mc must be positive")
    if not args.snr_levels:
        raise ValueError("--snr-levels must contain at least one value")
    if args.response_gain_jitter < 0.0:
        raise ValueError("--response-gain-jitter must be non-negative")
    if args.response_phase_jitter < 0.0:
        raise ValueError("--response-phase-jitter must be non-negative")
    if not 0.0 <= args.noise_correlation < 1.0:
        raise ValueError("--noise-correlation must be in [0, 1)")
    cfg = Q4V1Config(
        fs=args.fs,
        duration_s=duration_s,
        p_fa=args.p_fa,
        threshold_mc=threshold_mc,
        random_seed=args.seed,
        weight_mean_lambda=args.weight_mean_lambda,
        weight_trace_info=args.weight_trace_info,
        weight_min_eigen=args.weight_min_eigen,
        weight_redundancy=args.weight_redundancy,
        response_gain_jitter=args.response_gain_jitter,
        response_phase_jitter=args.response_phase_jitter,
        noise_correlation=args.noise_correlation,
        response_jitter_mode=args.response_jitter_mode,
        validation_weight_pd=args.validation_weight_pd,
        validation_weight_low_snr=args.validation_weight_low_snr,
        validation_weight_min_pd=args.validation_weight_min_pd,
        validation_weight_fa_excess=args.validation_weight_fa_excess,
    )
    context = run_experiments(
        cfg=cfg,
        grid_size=grid_size,
        top_layouts=top_layouts,
        runs=runs,
        false_alarm_runs=false_alarm_runs,
        snr_levels=tuple(args.snr_levels),
        profile=args.profile,
    )
    plots = write_all_outputs(args.output_dir, context)
    print(f"Q4 V1 completed: {args.output_dir.resolve()}")
    print(f"Paper outputs: {(args.output_dir / 'paper').resolve()}")
    print(f"Raw outputs: {(args.output_dir / 'raw').resolve()}")
    print(f"V1 selected layouts: {len(context['selected_layout_rows'])}")
    print(f"V1 PNG plots: {len(plots)}")
    print(f"Runtime seconds: {context['runtime_seconds']:.3f}")


if __name__ == "__main__":
    main()
