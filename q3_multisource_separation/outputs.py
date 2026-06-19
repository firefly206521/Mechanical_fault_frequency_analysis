"""CSV, PNG, and Markdown output helpers for Q3."""

from __future__ import annotations

import csv
import math
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from q2_harmonic_recovery.core import spectrum
from q2_harmonic_recovery.outputs import line_svg, residual_diagnostics_svg, write_csv


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def append_csv_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def convert_q3_svg_plots_to_png(output_dir: Path, remove_svg: bool = True) -> list[Path]:
    """Q3 wrapper matching Q2's Chromium renderer and image dimensions."""
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    browser = next((candidate for candidate in candidates if candidate.exists()), None)
    if browser is None:
        return []
    outputs = []
    with tempfile.TemporaryDirectory(prefix="q3_svg_render_") as profile:
        for svg in sorted(output_dir.glob("q3_*.svg")):
            header = svg.read_text(encoding="utf-8", errors="ignore")[:300]
            width_match = re.search(r'width="(\d+)"', header)
            height_match = re.search(r'height="(\d+)"', header)
            width = int(width_match.group(1)) if width_match else 1100
            height = int(height_match.group(1)) if height_match else 500
            png = svg.with_suffix(".png")
            command = [
                str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                f"--user-data-dir={profile}", "--force-device-scale-factor=1.8",
                f"--window-size={width},{height}", f"--screenshot={png}", svg.resolve().as_uri(),
            ]
            completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if completed.returncode == 0 and png.exists() and png.stat().st_size > 0:
                outputs.append(png)
                if remove_svg:
                    svg.unlink()
    return outputs


def write_plots(
    output_dir: Path,
    t: np.ndarray,
    y: np.ndarray,
    fit: dict,
    history: list[dict],
    segment_rows: list[dict],
    simulation_summary: list[dict],
    resolution_summary: list[dict],
    fs: float,
) -> list[Path]:
    zoom = t <= 10.0
    series = [("预处理信号", t[zoom], y[zoom], "#999999")]
    colors = ["#d62728", "#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]
    for index, component in enumerate(fit["components"]):
        series.append((f"分量{index + 1}: {component['frequency_hz']:.4f} Hz", t[zoom], component["waveform"][zoom], colors[index % len(colors)]))
    line_svg(output_dir / "q3_time_separated_components.svg", "Q3 多故障源分离（前10 s）", "时间 (s)", "幅值", series)

    f1, p1 = spectrum(y, fs)
    _, p2 = spectrum(fit["residual"], fs)
    mask = (f1 >= 0.05) & (f1 <= 49.5)
    line_svg(output_dir / "q3_spectrum_before_after.svg", "Q3 分离前后频谱对比", "频率 (Hz)", "功率（对数）", [
        ("分离前", f1[mask], p1[mask], "#777777"),
        ("联合残差", f1[mask], p2[mask], "#1f77b4"),
    ], log_y=True)

    residual_diagnostics_svg(output_dir / "q3_residual_diagnostics.svg", fit["residual"])

    accepted = [row for row in history if row.get("accepted")]
    if accepted:
        line_svg(output_dir / "q3_model_selection.svg", "Q3 自动定阶过程", "接受后的分量数", "BIC改善量", [
            ("BIC改善", np.arange(1, len(accepted) + 1), [row["bic_improvement"] for row in accepted], "#d62728"),
        ])

    for component_id in sorted({int(row["component_id"]) for row in segment_rows}):
        rows = [row for row in segment_rows if int(row["component_id"]) == component_id]
        centers = [(float(row["start_s"]) + float(row["end_s"])) / 2.0 for row in rows]
        if component_id == 1:
            segment_series = []
        segment_series.append((f"分量{component_id}", centers, [abs(float(row["frequency_deviation_hz"])) for row in rows], colors[(component_id - 1) % len(colors)]))
    if segment_rows:
        line_svg(output_dir / "q3_segment_frequency_stability.svg", "Q3 50 s分段频率稳定性", "时间 (s)", "频率绝对偏差 (Hz)", segment_series)

    if simulation_summary:
        line_svg(output_dir / "q3_simulation_order_accuracy.svg", "Q3 多源数量识别率", "总SNR (dB)", "正确率", [
            ("K识别正确率", [row["snr_total_db"] for row in simulation_summary], [row["correct_k_rate"] for row in simulation_summary], "#2ca02c"),
        ])
        line_svg(output_dir / "q3_simulation_errors.svg", "Q3 多源恢复误差", "总SNR (dB)", "误差", [
            ("频率MAE/Hz", [row["snr_total_db"] for row in simulation_summary], [row["mean_frequency_mae_hz_given_correct_k"] for row in simulation_summary], "#1f77b4"),
            ("波形RMSE", [row["snr_total_db"] for row in simulation_summary], [row["mean_waveform_rmse"] for row in simulation_summary], "#d62728"),
        ])

    if resolution_summary:
        resolution_series = []
        for case, color in [("equal", "#1f77b4"), ("unequal", "#d62728")]:
            rows = [row for row in resolution_summary if row["amplitude_case"] == case]
            resolution_series.append((f"主模型-{case}", [row["separation_hz"] for row in rows], [row["main_success_rate"] for row in rows], color))
            resolution_series.append((f"MUSIC-{case}", [row["separation_hz"] for row in rows], [row["music_success_rate"] for row in rows], "#2ca02c" if case == "equal" else "#9467bd"))
        line_svg(output_dir / "q3_resolution_probability.svg", "Q3 近频辨识概率", "频率间隔 (Hz)", "成功率", resolution_series)
        for case, color in [("equal", "#1f77b4"), ("unequal", "#d62728")]:
            rows = [row for row in resolution_summary if row["amplitude_case"] == case]
            if case == "equal":
                condition_series = []
            condition_series.append((case, [row["separation_hz"] for row in rows], [row["median_condition_design"] for row in rows], color))
        line_svg(output_dir / "q3_condition_vs_separation.svg", "Q3 设计矩阵条件数与频率间隔", "频率间隔 (Hz)", "条件数（对数）", condition_series, log_y=True)

    return convert_q3_svg_plots_to_png(output_dir, remove_svg=True)


def write_report(path: Path, context: dict) -> None:
    fit = context["fit"]
    components = context["components"]
    simulation = context["simulation_summary"]
    resolution = context["resolution_summary"]
    null_rows = context["null_rows"]
    false_alarm_rate = float(np.mean([str(row["false_alarm"]).lower() == "true" for row in null_rows])) if null_rows else float("nan")
    lines = [
        "# 第三问：多故障源分离与定位",
        "",
        "## 1. 模型",
        "",
        "本文将第一问的GLRT扩展为多峰顺序检测，并将第二问的谐波回归扩展为多频联合拟合。每加入一个候选分量，程序重新联合估计全部频率、振幅和相位；只有GLRT通过门限且BIC至少降低10时才保留该分量。",
        "",
        "联合最小二乘使用SVD，不显式计算正规方程的逆。程序同时记录设计矩阵条件数；条件数超过 $10^6$ 或数值秩不足时，不把结果认定为可靠分离。",
        "",
        "## 2. 真实数据分离结果",
        "",
        f"程序自动识别出{len(components)}个故障分量，联合模型解释方差为{fit['explained_variance']:.2%}，残差标准差为{np.std(fit['residual']):.6f}。",
        "",
        "| 分量 | 频率/Hz | 振幅 | 初相位/rad | 分量SNR/dB |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in components:
        lines.append(f"| {row['component_id']} | {row['frequency_hz']:.9f} | {row['amplitude']:.6f} | {row['phase_origin_rad']:.6f} | {row['component_snr_db']:.3f} |")
    lines += [
        "",
        f"设计矩阵条件数为{fit['condition_design']:.3g}，正规矩阵等效条件数为{fit['condition_normal']:.3g}。",
        "",
        "## 3. 多源数值实验",
        "",
        "总SNR定义为全部正弦分量功率之和与噪声功率之比；逐分量SNR另行写入试验明细CSV。",
        "",
        "| 总SNR/dB | 重复次数 | K识别正确率 | 95%区间 | 条件频率MAE/Hz | 条件振幅误差 | 条件相位MAE/rad | 波形RMSE |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in simulation:
        frequency_text = f"{row['mean_frequency_mae_hz_given_correct_k']:.6g}" if np.isfinite(row['mean_frequency_mae_hz_given_correct_k']) else "—"
        amplitude_text = f"{row['mean_amplitude_relative_error_given_correct_k']:.3%}" if np.isfinite(row['mean_amplitude_relative_error_given_correct_k']) else "—"
        phase_text = f"{row['mean_phase_mae_rad_given_correct_k']:.6g}" if np.isfinite(row['mean_phase_mae_rad_given_correct_k']) else "—"
        lines.append(f"| {row['snr_total_db']:.0f} | {row['runs']} | {row['correct_k_rate']:.1%} | [{row['correct_k_ci95_low']:.1%}, {row['correct_k_ci95_high']:.1%}] | {frequency_text} | {amplitude_text} | {phase_text} | {row['mean_waveform_rmse']:.6g} |")
    lines += [
        "",
        f"纯噪声顺序检测的经验误报率为{false_alarm_rate:.2%}。",
        "",
        "## 4. 近频辨识极限",
        "",
        "辨识成功要求自动识别两个分量、两个频率误差均不超过间隔的四分之一、设计矩阵条件数不超过 $10^6$ 且数值秩完整。经验极限取成功率达到90%并在更大间隔持续不低于90%的最小间隔。",
        "",
        "| 振幅条件 | 间隔/Hz | 主模型成功率 | 主模型95%区间 | MUSIC成功率 | 条件数中位数 | 建议追加实验 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in resolution:
        lines.append(f"| {row['amplitude_case']} | {row['separation_hz']:.6g} | {row['main_success_rate']:.1%} | [{row['main_ci95_low']:.1%}, {row['main_ci95_high']:.1%}] | {row['music_success_rate']:.1%} | {row['median_condition_design']:.3g} | {'是' if row['priority_for_more_runs'] else '否'} |")
    lines += [
        "",
        "FFT频点间隔 $1/T=0.0025$ Hz不是参数估计的绝对下限。联合参数模型可以在有利SNR下实现超分辨率，但频率接近时设计矩阵逐渐病态；频率完全相同时，只能识别两个正弦的矢量和。",
        "",
        "近频区域的局部线性化参数置信区间可能低估不确定性，因此本文以Monte Carlo经验成功率和Wilson区间作为主要依据。",
        "",
        "## 5. 结论",
        "",
        "多峰GLRT负责控制误报并提出候选频率，多频联合谐波回归负责分离波形和估计参数，BIC负责自动确定故障源数量。残差、分段稳定性、已知真值仿真和近频实验共同评价模型。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
