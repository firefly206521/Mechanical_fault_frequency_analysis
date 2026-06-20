"""Sequential overnight Q4 experiment launcher.

Use profiles to split long-running validation across two machines without
editing command lines by hand.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Job:
    name: str
    args: tuple[str, ...]


PC1_JOBS = (
    Job("baseline_long_seed20260619", (
        "--runs", "260", "--false-alarm-runs", "700", "--threshold-mc", "800",
        "--duration-s", "40", "--seed", "20260619",
        "--snr-levels", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
    Job("low_snr_dense_seed20260621", (
        "--runs", "300", "--false-alarm-runs", "700", "--threshold-mc", "800",
        "--duration-s", "40", "--seed", "20260621",
        "--snr-levels", "-30", "-27.5", "-25", "-22.5", "-20", "-17.5", "-15",
    )),
    Job("strict_false_alarm_seed20260623", (
        "--runs", "220", "--false-alarm-runs", "900", "--threshold-mc", "1200",
        "--duration-s", "40", "--seed", "20260623", "--p-fa", "0.01",
        "--snr-levels", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
)


PC2_JOBS = (
    Job("baseline_repeat_seed20260620", (
        "--runs", "260", "--false-alarm-runs", "700", "--threshold-mc", "800",
        "--duration-s", "40", "--seed", "20260620",
        "--snr-levels", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
    Job("long_window_seed20260622", (
        "--runs", "180", "--false-alarm-runs", "600", "--threshold-mc", "800",
        "--duration-s", "80", "--seed", "20260622",
        "--snr-levels", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
    Job("score_sensitivity_seed20260624", (
        "--runs", "220", "--false-alarm-runs", "700", "--threshold-mc", "800",
        "--duration-s", "40", "--seed", "20260624", "--lambda-pfa", "3.5", "--mu-balance", "1.2",
        "--snr-levels", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
)


EXPERIMENTAL_JOBS = (
    Job("balanced_only_reference", (
        "--runs", "350", "--false-alarm-runs", "900", "--threshold-mc", "1000",
        "--duration-s", "40", "--seed", "20260625", "--scenarios", "balanced",
        "--snr-levels", "-30", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
    Job("shadow_and_noise_stress", (
        "--runs", "320", "--false-alarm-runs", "900", "--threshold-mc", "1000",
        "--duration-s", "40", "--seed", "20260626",
        "--scenarios", "spatial_noise_skew", "source_shadow",
        "--snr-levels", "-30", "-25", "-20", "-15", "-12", "-10", "-5",
    )),
)


SMOKE_JOBS = (
    Job("smoke", (
        "--runs", "2", "--false-alarm-runs", "2", "--threshold-mc", "10",
        "--duration-s", "5", "--seed", "20260619", "--snr-levels", "-20", "-10",
    )),
)


PROFILES = {
    "pc1": PC1_JOBS,
    "pc2": PC2_JOBS,
    "experimental": EXPERIMENTAL_JOBS,
    "all": PC1_JOBS + PC2_JOBS + EXPERIMENTAL_JOBS,
    "smoke": SMOKE_JOBS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Q4 overnight experiment profiles")
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--root-output", type=Path, default=Path("q4_sensor_layout_results_overnight"))
    parser.add_argument("--start-at", default=None, help="Optional job name to resume a profile from")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    jobs = list(PROFILES[args.profile])
    if args.start_at:
        names = [job.name for job in jobs]
        if args.start_at not in names:
            raise SystemExit(f"--start-at must be one of: {', '.join(names)}")
        jobs = jobs[names.index(args.start_at):]

    args.root_output.mkdir(parents=True, exist_ok=True)
    log_path = args.root_output / f"{args.profile}_run_log.txt"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"profile={args.profile}\n")
        for job in jobs:
            output_dir = args.root_output / args.profile / job.name
            command = [
                sys.executable, "-m", "q4_sensor_layout.run_q4",
                "--output-dir", str(output_dir),
                *job.args,
            ]
            started = time.strftime("%Y-%m-%d %H:%M:%S")
            log.write(f"\n[{started}] START {job.name}\n")
            log.write(" ".join(command) + "\n")
            log.flush()
            completed = subprocess.run(command)
            ended = time.strftime("%Y-%m-%d %H:%M:%S")
            log.write(f"[{ended}] END {job.name} returncode={completed.returncode}\n")
            log.flush()
            if completed.returncode != 0:
                raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()

