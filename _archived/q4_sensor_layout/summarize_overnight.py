"""Summarize Q4 overnight experiment outputs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ._io import write_csv


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_runtime(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def discover_jobs(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*/*") if (path / "paper").is_dir() and (path / "raw").is_dir())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize Q4 overnight result folders")
    parser.add_argument("--root-output", type=Path, default=Path("q4_sensor_layout_results_overnight"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root_output
    job_rows = []
    top_rows = []
    benchmark_rows = []
    for job_dir in discover_jobs(root):
        profile = job_dir.parent.name
        job_name = job_dir.name
        runtime = read_runtime(job_dir / "raw" / "q4_runtime.txt")
        ranking = read_csv(job_dir / "paper" / "q4_layout_ranking.csv")
        snr = read_csv(job_dir / "paper" / "q4_snr_performance.csv")
        best = ranking[0] if ranking else {}
        job_rows.append({
            "profile": profile,
            "job_name": job_name,
            "best_layout": best.get("layout", ""),
            "best_score": best.get("score", ""),
            "best_mean_pd_source": best.get("mean_pd_source", ""),
            "best_low_snr_pd_source": best.get("low_snr_pd_source", ""),
            "best_mean_p_fa": best.get("mean_p_fa", ""),
            "runs": runtime.get("runs", ""),
            "false_alarm_runs": runtime.get("false_alarm_runs", ""),
            "threshold_mc": runtime.get("threshold_mc", ""),
            "duration_s": runtime.get("duration_s", ""),
            "p_fa": runtime.get("p_fa", ""),
            "lambda_pfa": runtime.get("lambda_pfa", ""),
            "mu_balance": runtime.get("mu_balance", ""),
            "random_seed": runtime.get("random_seed", ""),
            "scenario_names": runtime.get("scenario_names", ""),
            "snr_levels": runtime.get("snr_levels", ""),
            "runtime_seconds": runtime.get("runtime_seconds", ""),
        })
        for row in ranking[:10]:
            top_rows.append({"profile": profile, "job_name": job_name, **row})
        for row in snr:
            benchmark_rows.append({"profile": profile, "job_name": job_name, **row})

    summary_dir = root / "_summary"
    write_csv(summary_dir / "q4_overnight_job_summary.csv", job_rows)
    write_csv(summary_dir / "q4_overnight_top_layouts.csv", top_rows)
    write_csv(summary_dir / "q4_overnight_benchmark_snr.csv", benchmark_rows)
    print(f"Jobs summarized: {len(job_rows)}")
    print(f"Summary: {summary_dir.resolve()}")


if __name__ == "__main__":
    main()
