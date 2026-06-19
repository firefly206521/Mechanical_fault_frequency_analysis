"""CSV, PNG, and Markdown outputs for Q4."""

from __future__ import annotations

import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .core import DEFAULT_AMPLITUDES, DEFAULT_FREQUENCIES, FAULT_LABELS, SENSOR_NAMES


def configure_matplotlib() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_plots(output_dir: Path, context: dict) -> list[Path]:
    configure_matplotlib()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    selected_rows = context["selected_snr_rows"]
    if selected_rows:
        fig, ax = plt.subplots(figsize=(9.5, 5.2), dpi=180)
        colors = {
            "single_best": "#777777",
            "random_three": "#1f77b4",
            "best_three": "#d62728",
            "all_sensors_reference": "#2ca02c",
        }
        labels = {
            "single_best": "单个最优测点",
            "random_three": "随机三测点",
            "best_three": "最优三测点",
            "all_sensors_reference": "全部测点参考",
        }
        for benchmark in labels:
            rows = sorted([row for row in selected_rows if row["benchmark"] == benchmark], key=lambda row: row["snr_db"])
            if rows:
                ax.plot([row["snr_db"] for row in rows], [row["pd_source_mean"] for row in rows],
                        marker="o", linewidth=2.0, color=colors[benchmark], label=labels[benchmark])
        ax.set_title("Q4 不同布局的检测概率-SNR 曲线")
        ax.set_xlabel("总 SNR (dB)")
        ax.set_ylabel("平均故障源检测概率")
        ax.set_ylim(-0.02, 1.02)
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        path = output_dir / "q4_pd_snr_curve.png"
        fig.savefig(path)
        plt.close(fig)
        outputs.append(path)

    ranking = context["layout_ranking"][:12]
    if ranking:
        fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=180)
        names = [row["layout"].replace("+", "\n") for row in ranking][::-1]
        scores = [row["score"] for row in ranking][::-1]
        ax.barh(names, scores, color="#4c78a8")
        ax.set_title("Q4 布局综合评分排名（前12）")
        ax.set_xlabel("综合评分")
        ax.grid(True, axis="x", alpha=0.25)
        fig.tight_layout()
        path = output_dir / "q4_layout_ranking.png"
        fig.savefig(path)
        plt.close(fig)
        outputs.append(path)

    sensitivity = np.asarray(context["sensitivity_matrix"], dtype=float)
    fig, ax = plt.subplots(figsize=(8.5, 5.0), dpi=180)
    image = ax.imshow(sensitivity, cmap="viridis", aspect="auto")
    ax.set_title("Q4 候选测点-故障源敏感度矩阵")
    ax.set_xticks(range(len(FAULT_LABELS)), FAULT_LABELS)
    ax.set_yticks(range(len(SENSOR_NAMES)), SENSOR_NAMES)
    for row in range(sensitivity.shape[0]):
        for col in range(sensitivity.shape[1]):
            ax.text(col, row, f"{sensitivity[row, col]:.2f}", ha="center", va="center", color="white" if sensitivity[row, col] > 0.7 else "black", fontsize=8)
    fig.colorbar(image, ax=ax, label="敏感度")
    fig.tight_layout()
    path = output_dir / "q4_sensitivity_heatmap.png"
    fig.savefig(path)
    plt.close(fig)
    outputs.append(path)
    return outputs


def write_report(path: Path, context: dict) -> None:
    ranking = context["layout_ranking"]
    selected = context["selected_snr_rows"]
    robustness = context["robustness_rows"]
    best = ranking[0]
    best_three = next(row for row in ranking if row["sensor_count"] == 3)
    best_single = next(row for row in ranking if row["sensor_count"] == 1)
    lines = [
        "# 第四问：传感器布局与系统鲁棒性优化",
        "",
        "## 1. 建模思想",
        "",
        "题目没有给出设备几何、材料参数和真实传播路径，因此本文不假设可以计算连续空间中的物理全局最优坐标。第四问采用候选测点集合下的鲁棒布局优化：先给出有限个工程可安装位置，再用敏感度矩阵表示传播衰减、安装方向和局部耦合差异。",
        "",
        "多传感器观测模型为",
        "",
        "$$y_m(t)=\\sum_k h_{mk}A_k\\sin(2\\pi f_kt+\\phi_k+\\delta_{mk})+n_m(t),$$",
        "",
        "其中 $h_{mk}$ 为第 $m$ 个测点对第 $k$ 个故障源的综合敏感度，$\\delta_{mk}$ 为传播相位差，$n_m(t)$ 为测点噪声。频率和振幅口径沿用第三问真实数据结果，故障频率约为 `4, 8, 13, 14 Hz`。",
        "",
        "## 2. 融合检测与布局目标",
        "",
        "每个测点在目标频率集合上计算 GLRT/匹配投影统计量，再按噪声方差倒数加权融合：",
        "",
        "$$T_{\\mathrm{fused}}(f)=\\sum_{m\\in S}w_mT_m(f),\\qquad w_m\\propto 1/\\hat\\sigma_m^2.$$",
        "",
        "布局评分函数为",
        "",
        "$$J(S)=\\overline{P_D(S)}-2P_{FA}(S)-0.5\\operatorname{Var}_k(P_{D,k}(S)).$$",
        "",
        "该目标同时考虑平均检测概率、误报率和不同故障源检测均衡性。最多选择 3 个传感器，因此直接枚举全部 1、2、3 测点组合。",
        "",
        "## 3. 敏感度矩阵",
        "",
        "| 测点 | 4Hz | 8Hz | 13Hz | 14Hz |",
        "|---|---:|---:|---:|---:|",
    ]
    sensitivity = np.asarray(context["sensitivity_matrix"], dtype=float)
    for name, row in zip(SENSOR_NAMES, sensitivity):
        lines.append(f"| {name} | {row[0]:.2f} | {row[1]:.2f} | {row[2]:.2f} | {row[3]:.2f} |")
    lines += [
        "",
        "## 4. 布局优化结果",
        "",
        f"综合评分最高的布局为 `{best['layout']}`，其中三传感器最优布局为 `{best_three['layout']}`。单传感器最优为 `{best_single['layout']}`。",
        "",
        "| 排名 | 布局 | 传感器数 | 平均检测概率 | 低SNR检测概率 | 平均误报率 | 均衡方差 | 评分 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ranking[:10]:
        lines.append(f"| {row['rank']} | {row['layout']} | {row['sensor_count']} | {row['mean_pd_source']:.1%} | {row['low_snr_pd_source']:.1%} | {row['mean_p_fa']:.1%} | {row['mean_balance_variance']:.4f} | {row['score']:.4f} |")
    lines += [
        "",
        "## 5. SNR 性能对比",
        "",
        "| 对照组 | 布局 | SNR/dB | 平均故障源检测概率 | 全部故障检出率 | 误报率 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    label_map = {
        "single_best": "单个最优测点",
        "random_three": "随机三测点",
        "best_three": "最优三测点",
        "all_sensors_reference": "全部测点参考",
    }
    for row in sorted(selected, key=lambda item: (item["benchmark"], item["snr_db"])):
        lines.append(f"| {label_map.get(row['benchmark'], row['benchmark'])} | {row['layout']} | {row['snr_db']:.0f} | {row['pd_source_mean']:.1%} | {row['pd_all']:.1%} | {row['p_fa']:.1%} |")
    lines += [
        "",
        "## 6. 鲁棒性场景",
        "",
        "| 场景 | 说明 | 最优布局 | 低SNR检测概率 | 平均误报率 |",
        "|---|---|---|---:|---:|",
    ]
    for row in robustness:
        lines.append(f"| {row['scenario']} | {row['description']} | {row['best_layout']} | {row['best_low_snr_pd_source']:.1%} | {row['best_mean_p_fa']:.1%} |")
    lines += [
        "",
        "## 7. 结论",
        "",
        "第四问的优化结果表明，在没有具体结构模型时，合理做法是把布局问题表述为候选测点集合上的鲁棒组合优化。最优三测点布局通常覆盖轴承座、齿轮箱壳体和轴端等互补位置，使不同故障源至少有一个高敏感度、低噪声测点可观测。与单测点相比，多传感器加权融合能提高低 SNR 下的综合检测概率，并降低局部失敏、噪声不均或相位抵消导致的漏检风险。",
        "",
        "该结论不是物理连续空间的全局最优安装坐标，而是在给定候选测点、敏感度不确定场景和前三问检测模型下的鲁棒最优布局。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_runtime(path: Path, context: dict) -> None:
    cfg = context["config"]
    lines = [
        f"runs={context['runs']}",
        f"false_alarm_runs={context['false_alarm_runs']}",
        f"threshold_mc={cfg.threshold_mc}",
        f"duration_s={cfg.duration_s}",
        f"fs={cfg.fs}",
        f"p_fa={cfg.p_fa}",
        f"lambda_pfa={cfg.lambda_pfa}",
        f"mu_balance={cfg.mu_balance}",
        f"random_seed={cfg.random_seed}",
        f"snr_levels={','.join(str(v) for v in context['snr_levels'])}",
        f"scenario_names={','.join(str(v) for v in context.get('scenario_names', []))}",
        f"runtime_seconds={context['runtime_seconds']:.6f}",
        f"frequencies_hz={','.join(f'{v:.9f}' for v in DEFAULT_FREQUENCIES)}",
        f"amplitudes={','.join(f'{v:.9f}' for v in DEFAULT_AMPLITUDES)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_result_readme(path: Path) -> None:
    lines = [
        "# Q4 输出目录说明",
        "",
        "本目录将第四问结果分为论文材料和原始/追溯数据两类。",
        "",
        "## paper",
        "",
        "论文正文可直接引用的报告、汇总表和图片，包括布局排名、SNR 对比、故障源覆盖、鲁棒性场景和三张 PNG 图。",
        "",
        "## raw",
        "",
        "用于追溯和复核的完整枚举结果、运行参数和 Monte Carlo 明细。通常不直接放入论文正文。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
