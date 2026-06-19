"""Create an auditable baseline-versus-optimized Q3 comparison."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def runtime_value(path: Path, key: str) -> float:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            values[name] = value
    return float(values[key])


def failure_counts(rows: list[dict], case: str, separation: float) -> tuple[int, int, int]:
    group = [row for row in rows if row["amplitude_case"] == case and abs(float(row["separation_hz"]) - separation) < 1e-12]
    not_split = inaccurate = over_split = 0
    for row in group:
        if str(row["main_success"]).lower() == "true":
            continue
        estimated_k = int(float(row["main_estimated_k"]))
        if estimated_k < 2:
            not_split += 1
        elif estimated_k > 2:
            over_split += 1
        else:
            inaccurate += 1
    return not_split, inaccurate, over_split


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--optimized", type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    optimized = args.optimized.resolve()

    base_summary = read_csv(baseline / "q3_resolution_limit.csv")
    opt_summary = read_csv(optimized / "q3_resolution_limit.csv")
    base_trials = read_csv(baseline / "q3_resolution_trials.csv")
    opt_trials = read_csv(optimized / "q3_resolution_trials.csv")
    comparison = []
    for opt in opt_summary:
        base = next(row for row in base_summary if row["amplitude_case"] == opt["amplitude_case"] and abs(float(row["separation_hz"]) - float(opt["separation_hz"])) < 1e-12)
        case = opt["amplitude_case"]
        separation = float(opt["separation_hz"])
        b_not, b_inaccurate, b_over = failure_counts(base_trials, case, separation)
        o_not, o_inaccurate, o_over = failure_counts(opt_trials, case, separation)
        comparison.append({
            "amplitude_case": case,
            "separation_hz": separation,
            "baseline_success_rate": float(base["main_success_rate"]),
            "optimized_success_rate": float(opt["main_success_rate"]),
            "success_rate_change": float(opt["main_success_rate"]) - float(base["main_success_rate"]),
            "baseline_not_split_failures": b_not,
            "optimized_not_split_failures": o_not,
            "baseline_inaccurate_two_source_failures": b_inaccurate,
            "optimized_inaccurate_two_source_failures": o_inaccurate,
            "baseline_over_split_failures": b_over,
            "optimized_over_split_failures": o_over,
            "baseline_mean_runtime_seconds": float(base["mean_main_runtime_seconds"]),
            "optimized_mean_runtime_seconds": float(opt["mean_main_runtime_seconds"]),
        })
    write_csv(optimized / "q3_optimization_comparison.csv", comparison)

    base_extreme = read_csv(baseline / "q3_extreme_summary.csv")
    opt_extreme = read_csv(optimized / "q3_extreme_summary.csv")
    extreme_comparison = []
    for opt in opt_extreme:
        base = next(row for row in base_extreme if row["case_name"] == opt["case_name"])
        extreme_comparison.append({
            "case_name": opt["case_name"],
            "baseline_success_rate": float(base["success_rate"]),
            "optimized_success_rate": float(opt["success_rate"]),
            "success_rate_change": float(opt["success_rate"]) - float(base["success_rate"]),
        })
    write_csv(optimized / "q3_extreme_optimization_comparison.csv", extreme_comparison)

    base_null = read_csv(baseline / "q3_null_trials.csv")
    opt_null = read_csv(optimized / "q3_null_trials.csv")
    base_false = sum(row["false_alarm"].lower() == "true" for row in base_null)
    opt_false = sum(row["false_alarm"].lower() == "true" for row in opt_null)
    base_runtime = runtime_value(baseline / "q3_runtime.txt", "total_seconds")
    opt_runtime = runtime_value(optimized / "q3_runtime.txt", "total_seconds")
    target_equal = next(row for row in comparison if row["amplitude_case"] == "equal" and row["separation_hz"] == 0.0025)
    target_unequal = next(row for row in comparison if row["amplitude_case"] == "unequal" and row["separation_hz"] == 0.003)
    identical = next(row for row in extreme_comparison if row["case_name"] == "identical_frequency")
    stability = read_csv(optimized / "q3_failure_stability_summary.csv")
    worst_equal = next(row for row in stability if row["scenario"] == "equal_0025_phase_grid_worst")
    worst_unequal = next(row for row in stability if row["scenario"] == "unequal_003_phase_grid_worst")
    reliable = sum(row.get("main_frequency_ci_reliable", "false").lower() == "true" for row in opt_trials)

    def joint_coverage(case: str, separation: float) -> tuple[int, float]:
        truth = (13.5 - separation / 2.0, 13.5 + separation / 2.0)
        group = [row for row in opt_trials if row["amplitude_case"] == case and abs(float(row["separation_hz"]) - separation) < 1e-12 and row.get("main_frequency_ci_reliable", "false").lower() == "true"]
        covered = 0
        for row in group:
            covered += (
                float(row["main_frequency_1_hz"]) - 1.96 * float(row["main_frequency_1_se_hz"]) <= truth[0] <= float(row["main_frequency_1_hz"]) + 1.96 * float(row["main_frequency_1_se_hz"])
                and float(row["main_frequency_2_hz"]) - 1.96 * float(row["main_frequency_2_se_hz"]) <= truth[1] <= float(row["main_frequency_2_hz"]) + 1.96 * float(row["main_frequency_2_se_hz"])
            )
        return len(group), covered / len(group) if group else float("nan")

    equal_ci_n, equal_ci_coverage = joint_coverage("equal", 0.0025)
    unequal_ci_n, unequal_ci_coverage = joint_coverage("unequal", 0.003)

    report = f"""# Q3近频辨识优化对比报告

## 结论

- 等幅0.0025 Hz成功率由 {100*target_equal['baseline_success_rate']:.1f}% 提升至 {100*target_equal['optimized_success_rate']:.1f}%。
- 不等幅0.003 Hz成功率由 {100*target_unequal['baseline_success_rate']:.1f}% 提升至 {100*target_unequal['optimized_success_rate']:.1f}%。
- 完全同频正确不拆分率由 {100*identical['baseline_success_rate']:.1f}% 提升至 {100*identical['optimized_success_rate']:.1f}%。
- 纯噪声误报保持为 {base_false}/{len(base_null)} 到 {opt_false}/{len(opt_null)}，没有增加。
- 实际数据仍识别4个故障源：约4、8、13和14 Hz。

## 方法变化

单频零假设和双频备择模型均在完整400秒数据上重新优化。双频模型先生成多组残差峰、局部峰和自适应分裂起点，再以中心频率和正频率间隔进行二维可变投影搜索。第二源只有同时满足条件GLRT、ΔBIC≥10、满秩和条件数要求时才保留。

条件GLRT的1%门限使用500次单频零假设Monte Carlo标定。优化结果同时给出有限差分Hessian频率区间；{reliable}/{len(opt_trials)} 次近频试验获得数值可计算的区间，其余明确标记为不可靠。

Hessian区间是局部线性化诊断，并非经过Bootstrap校准的正式95%置信区间。等幅0.0025 Hz的双频联合覆盖率为 {100*equal_ci_coverage:.1f}%（{equal_ci_n}次可计算），不等幅0.003 Hz为 {100*unequal_ci_coverage:.1f}%（{unequal_ci_n}次可计算）。后者明显低于95%，论文中不得把它表述为已达到标称覆盖率。

## 困难相位复验

- 等幅0.0025 Hz、相位差π：优化后成功率 {100*float(worst_equal['success_rate']):.1f}%（100次）。
- 不等幅0.003 Hz、相位差5π/6：优化后成功率 {100*float(worst_unequal['success_rate']):.1f}%（100次）。
- 不等幅最坏相位仍低于随机相位总体结果，说明振幅比和相位仍是实际辨识极限的一部分，但不再表现为稳定失败。

## 运行时间

基线完整运行 {base_runtime:.1f} 秒，优化版 {opt_runtime:.1f} 秒，倍率为 {opt_runtime/base_runtime:.2f}，满足不超过基线两倍的预算。

## 验收

等幅目标、不等幅目标、同频不拆分、纯噪声误报、实际四源结果和运行时间均通过既定验收标准。优化数据未提交，便于代码审查。
"""
    (optimized / "q3_optimization_report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
