"""Output generation for Q4 V1 adaptive sensor layout."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from ._io import write_csv


def _configure_chinese_font() -> None:
    font_paths = [
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/Deng.ttf"),
        Path("C:/Windows/Fonts/simsunb.ttf"),
    ]
    for font_path in font_paths:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=str(font_path)).get_name()]
            plt.rcParams["axes.unicode_minus"] = False
            return


def write_result_readme(path: Path, context: dict) -> None:
    text = f"""# Q4 V1 Adaptive Sensor Layout Results

This directory is the Q4 V1 result tree. All generated files use the `q4_v1_` prefix.

- `paper/` contains paper-facing V1 summaries, tables, figures, and report text.
- `raw/` contains V1 candidate points, prescreen scores, Monte Carlo trial rows, and runtime metadata.
- Q4 V0 authoritative overnight results remain in `q4_sensor_layout_results_overnight/`.

V1 is an adaptive layout optimization under a parameterized structural example. The coordinates are dimensionless model coordinates, not real-machine installation coordinates.

Run profile: `{context["profile"]}`
Grid size: `{context["grid_size"]}`
Random seed: `{context["config"].random_seed}`
Objective weights: detection_mean_lambda `{context["config"].weight_mean_lambda}`, trace_info `{context["config"].weight_trace_info}`, min_eigen `{context["config"].weight_min_eigen}`, scaled_redundancy `{context["config"].weight_redundancy}`
Robustness scenario: response_gain_jitter `{context["config"].response_gain_jitter}`, response_phase_jitter `{context["config"].response_phase_jitter}`, noise_correlation `{context["config"].noise_correlation}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_runtime(path: Path, context: dict) -> None:
    cfg = context["config"]
    lines = [
        "Q4 V1 runtime and parameters",
        f"profile={context['profile']}",
        f"runtime_seconds={context['runtime_seconds']:.6f}",
        f"grid_size={context['grid_size']}",
        f"top_layouts={context['top_layouts']}",
        f"runs={context['runs']}",
        f"false_alarm_runs={context['false_alarm_runs']}",
        f"snr_levels={','.join(str(v) for v in context['snr_levels'])}",
        f"fs={cfg.fs}",
        f"duration_s={cfg.duration_s}",
        f"p_fa={cfg.p_fa}",
        f"threshold_mc={cfg.threshold_mc}",
        f"random_seed={cfg.random_seed}",
        f"redundancy_limit={cfg.redundancy_limit}",
        f"prescreen_max={cfg.prescreen_max}",
        f"weight_mean_lambda={cfg.weight_mean_lambda}",
        f"weight_trace_info={cfg.weight_trace_info}",
        f"weight_min_eigen={cfg.weight_min_eigen}",
        f"weight_redundancy={cfg.weight_redundancy}",
        f"eig_regularization={cfg.eig_regularization}",
        f"similarity_floor={cfg.similarity_floor}",
        f"swap_max_iter_factor={cfg.swap_max_iter_factor}",
        f"response_gain_jitter={cfg.response_gain_jitter}",
        f"response_phase_jitter={cfg.response_phase_jitter}",
        f"noise_correlation={cfg.noise_correlation}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_report(path: Path, context: dict) -> None:
    best = context["selected_layout_rows"][0] if context["selected_layout_rows"] else {}
    validated = context["validated_layout_rows"][0] if context["validated_layout_rows"] else {}
    mesh = context["mesh_rows"][0] if context["mesh_rows"] else {}
    text = f"""# Q4 V1 自适应传感器布局报告

## 结果口径

本报告为 Q4 V1。V1 使用参数化结构示例和自适应候选网格来选择最多 3 个传感器位置；坐标是无量纲模型坐标，不是真实设备安装坐标。Q4 V0 的权威过夜结果仍位于 `q4_sensor_layout_results_overnight/`，在 V1 中只作为有限候选区域基线参考。

## 模型

候选测点由可安装表面网格生成。每个测点记录区域、坐标、安装方向、噪声水平和对约 `4, 8, 13, 14 Hz` 故障频率的复响应。布局目标采用白化响应下的非中心参数：

$$\\lambda_k(S)=A_k^2 h_{{S,k}}^H \\Sigma_S^{{-1}} h_{{S,k}}.$$

V1 优先最大化最弱故障源的融合 GLRT 代理检测能力。代理量先按照噪声方差给每个传感器加权，再计算每个故障频率的等效非中心参数，因此比单纯累加白化响应更接近后续 Monte Carlo 检测器。

当前目标函数权重为：`detection_mean_lambda={context["config"].weight_mean_lambda}`，`trace_info={context["config"].weight_trace_info}`，`min_eigen={context["config"].weight_min_eigen}`，`scaled_redundancy={context["config"].weight_redundancy}`。其中冗余惩罚按融合检测强度缩放，不再使用绝对无量纲惩罚。

## 搜索流程

1. 生成 V1 参数化候选点。
2. 用单点白化响应和噪声水平预筛选。
3. 用 greedy 选点，再用 one-swap 局部搜索修正。
4. 在小规模候选集上执行完整枚举，验证 greedy + swap 的目标差距。
5. 只对前若干布局和基线布局运行 GLRT Monte Carlo。

## 当前运行

- profile: `{context["profile"]}`
- grid size: `{context["grid_size"]}`
- response gain jitter: `{context["config"].response_gain_jitter}`
- response phase jitter: `{context["config"].response_phase_jitter}`
- noise correlation: `{context["config"].noise_correlation}`
- prescreen count: `{mesh.get("prescreen_count", "")}`
- greedy+swap 到完整枚举最优的相对差距: `{mesh.get("greedy_swap_gap_to_exhaustive", float("nan")):.6f}`
- 最优 V1 布局: `{best.get("layout", "")}`
- 最优 V1 区域: `{best.get("regions", "")}`
- 最优目标值: `{best.get("objective", float("nan")):.6g}`
- Monte Carlo 验证最优布局: `{validated.get("layout", "")}`
- Monte Carlo 验证最优区域: `{validated.get("regions", "")}`
- Monte Carlo 验证分数: `{validated.get("validation_score", float("nan")):.6f}`

## 结论

V1 给出了“参数化结构示例下的稳定区域选择方法”。解析目标用于快速缩小候选布局，Monte Carlo 验证排序用于最终比较候选布局在检测率、低 SNR 表现、最弱源平衡和误报率上的综合表现。若后续有真实设备几何、有限元频响或移动传感器标定数据，只需要替换候选点响应矩阵和噪声协方差，布局搜索与 Monte Carlo 验证流程可以保持不变。

## 限制

- 当前坐标不代表真实机器坐标。
- 当前传播响应是简化参数化模型，不是有限元模型。
- smoke 结果只用于验证流程；是否进入论文主线需要 medium 或 official 结果支持。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_plots(paper_dir: Path, context: dict) -> list[Path]:
    _configure_chinese_font()
    paper_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        _plot_pd_curve(paper_dir / "q4_v1_pd_snr_curve.png", context),
        _plot_layout_heatmap(paper_dir / "q4_v1_layout_heatmap.png", context),
    ]
    return paths


def _plot_pd_curve(path: Path, context: dict) -> Path:
    rows = context["detection_summary"]
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["v1_adaptive_best", "v1_v0_region_baseline", "v1_random_three", "v1_max_response_three", "v1_spaced_three"]
    for label in labels:
        group = [row for row in rows if row["benchmark"] == label]
        if not group:
            continue
        by_snr = {}
        for row in group:
            by_snr.setdefault(float(row["snr_db"]), []).append(float(row["pd_source_mean"]))
        xs = sorted(by_snr)
        ys = [float(np.mean(by_snr[x])) for x in xs]
        ax.plot(xs, ys, marker="o", label=label.replace("v1_", "V1 "))
    ax.set_title("Q4 V1 检测概率-SNR 曲线")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("平均检测概率")
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def _plot_layout_heatmap(path: Path, context: dict) -> Path:
    candidate_rows = context["candidate_rows"]
    selected = set()
    if context["selected_layout_rows"]:
        selected = set(context["selected_layout_rows"][0]["layout"].split("+"))
    xs = np.asarray([row["x"] for row in candidate_rows], dtype=float)
    ys = np.asarray([row["y"] for row in candidate_rows], dtype=float)
    colors = np.asarray([row["response_abs_14Hz"] / max(row["noise_std"], 1e-12) for row in candidate_rows], dtype=float)
    fig, ax = plt.subplots(figsize=(7, 5))
    scatter = ax.scatter(xs, ys, c=colors, cmap="viridis", s=55, alpha=0.85, label="V1 候选点")
    chosen = [row for row in candidate_rows if row["point_id"] in selected]
    if chosen:
        ax.scatter([row["x"] for row in chosen], [row["y"] for row in chosen], c="red", s=130, marker="*", label="V1 选中点")
    ax.set_title("Q4 V1 候选点响应热力图")
    ax.set_xlabel("无量纲 x")
    ax.set_ylabel("无量纲 y")
    ax.legend()
    fig.colorbar(scatter, ax=ax, label="14Hz 白化响应强度")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def write_all_outputs(output_dir: Path, context: dict) -> list[Path]:
    paper_dir = output_dir / "paper"
    raw_dir = output_dir / "raw"
    paper_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    write_result_readme(output_dir / "README.md", context)
    write_csv(paper_dir / "q4_v1_selected_regions.csv", context["selected_layout_rows"])
    write_csv(paper_dir / "q4_v1_validated_layouts.csv", context["validated_layout_rows"])
    write_csv(paper_dir / "q4_v1_mesh_convergence.csv", context["mesh_rows"])
    write_csv(paper_dir / "q4_v1_robust_detection.csv", context["detection_summary"])
    write_report(paper_dir / "q4_v1_adaptive_report.md", context)
    plot_paths = write_plots(paper_dir, context)
    write_csv(raw_dir / "q4_v1_candidate_points.csv", context["candidate_rows"])
    write_csv(raw_dir / "q4_v1_prescreen_scores.csv", context["prescreen_rows"])
    write_csv(raw_dir / "q4_v1_layout_trials.csv", context["trial_rows"])
    write_runtime(raw_dir / "q4_v1_runtime.txt", context)
    return plot_paths
