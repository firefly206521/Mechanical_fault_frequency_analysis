"""
Q1 final GLRT model for weak sinusoidal fault-frequency detection.

This script focuses on the selected Q1 method after model comparison:
matched filtering / GLRT with Monte Carlo false-alarm threshold control.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from scipy import stats

from q1_model_compare import (
    Config,
    SHEET_SINGLE,
    estimate_glrt_threshold,
    estimate_sinusoid,
    fft_spectrum,
    frequency_bounds,
    glrt_stat_from_fft,
    load_single_source,
    preprocess,
    refine_frequency,
)


def configure_plot_fonts() -> None:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ["Microsoft YaHei", "SimHei", "SimSun"]:
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name]
            break
    plt.rcParams["axes.unicode_minus"] = False


GLRT_PARAMETERS = {
    "signal_model": "x(t)=A sin(2*pi*f*t+phi)+n(t)",
    "preprocess": "linear detrend",
    "frequency_search_min_hz": 0.05,
    "frequency_search_max_hz": 49.5,
    "target_false_alarm_rate": 0.05,
    "threshold_method": "pure-noise Monte Carlo on max GLRT statistic",
    "frequency_refinement": "bounded 1D least-squares around coarse FFT-bin peak",
}


def run_glrt_q1(cfg: Config) -> dict[str, float | bool | str]:
    t, x, fs = load_single_source(cfg.data_path)
    y = preprocess(x)

    freqs, stat = glrt_stat_from_fft(y, fs, cfg)
    mask = frequency_bounds(freqs, cfg)
    search_freqs = freqs[mask]
    search_stat = stat[mask]
    best_local = int(np.argmax(search_stat))
    coarse_freq = float(search_freqs[best_local])
    score = float(search_stat[best_local])
    threshold = estimate_glrt_threshold(len(y), fs, cfg)

    refined = refine_frequency(t, y, coarse_freq, fs)
    model_at_refined = estimate_sinusoid(t, y, refined["frequency"])
    detected = score >= threshold

    return {
        "detected": bool(detected),
        "coarse_frequency_hz": coarse_freq,
        "refined_frequency_hz": refined["frequency"],
        "glrt_score": score,
        "threshold": threshold,
        "p_fa_target": cfg.p_fa,
        "amplitude_for_reference": model_at_refined["amplitude"],
        "phase_for_reference_rad": model_at_refined["phase"],
        "fit_rmse": model_at_refined["rmse"],
        "fit_explained_var": model_at_refined["explained_var"],
        "sample_count": len(y),
        "sampling_rate_hz": fs,
        "decision": "fault frequency detected" if detected else "no significant fault frequency",
    }


def glrt_detect_signal(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict[str, float | bool]:
    y = preprocess(x)
    freqs, stat = glrt_stat_from_fft(y, fs, cfg)
    mask = frequency_bounds(freqs, cfg)
    search_freqs = freqs[mask]
    search_stat = stat[mask]
    best_local = int(np.argmax(search_stat))
    coarse_freq = float(search_freqs[best_local])
    score = float(search_stat[best_local])
    threshold = estimate_glrt_threshold(len(y), fs, cfg)
    refined = refine_frequency(t, y, coarse_freq, fs)
    return {
        "detected": bool(score >= threshold),
        "coarse_frequency_hz": coarse_freq,
        "refined_frequency_hz": refined["frequency"],
        "score": score,
        "threshold": threshold,
        "amplitude": refined["amplitude"],
        "phase": refined["phase"],
        "fit_rmse": refined["rmse"],
    }


def fft_peak_detect_signal(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict[str, float | bool]:
    y = preprocess(x)
    freqs, power = fft_spectrum(y, fs)
    mask = frequency_bounds(freqs, cfg)
    idx = np.where(mask)[0][np.argmax(power[mask])]
    coarse_freq = float(freqs[idx])
    refined = refine_frequency(t, y, coarse_freq, fs)
    return {
        "detected": True,
        "coarse_frequency_hz": coarse_freq,
        "refined_frequency_hz": refined["frequency"],
        "score": float(power[idx]),
        "threshold": np.nan,
        "amplitude": refined["amplitude"],
        "phase": refined["phase"],
        "fit_rmse": refined["rmse"],
    }


def analyze_preprocessing_and_noise(cfg: Config, result: dict[str, float | bool | str]) -> pd.DataFrame:
    t, x, fs = load_single_source(cfg.data_path)
    y = preprocess(x)
    s_hat = recovered_signal(t, x, float(result["refined_frequency_hz"]))
    residual = y - s_hat
    signal_power = float(np.mean(s_hat * s_hat))
    residual_power = float(np.mean(residual * residual))
    estimated_snr_db = 10.0 * math.log10(signal_power / residual_power)

    rows = [
        {"metric": "sample_count", "value": len(x), "note": "number of samples"},
        {"metric": "sampling_rate_hz", "value": fs, "note": "from Excel time column"},
        {"metric": "duration_s", "value": t[-1] - t[0], "note": "observation length"},
        {"metric": "raw_mean", "value": float(np.mean(x)), "note": "before preprocessing"},
        {"metric": "raw_std", "value": float(np.std(x)), "note": "before preprocessing"},
        {"metric": "preprocessed_mean", "value": float(np.mean(y)), "note": "after linear detrend"},
        {"metric": "preprocessed_std", "value": float(np.std(y)), "note": "after linear detrend"},
        {"metric": "residual_mean", "value": float(np.mean(residual)), "note": "after removing fitted 2 Hz sinusoid"},
        {"metric": "residual_std", "value": float(np.std(residual)), "note": "noise estimate"},
        {"metric": "residual_skewness", "value": float(stats.skew(residual)), "note": "near 0 supports symmetric noise"},
        {"metric": "residual_excess_kurtosis", "value": float(stats.kurtosis(residual)), "note": "near 0 supports Gaussian-like noise"},
        {"metric": "fitted_signal_rms", "value": float(np.sqrt(signal_power)), "note": "RMS of extracted sinusoid"},
        {"metric": "estimated_noise_rms", "value": float(np.sqrt(residual_power)), "note": "RMS of residual"},
        {"metric": "estimated_snr_db", "value": estimated_snr_db, "note": "10log10(signal_power/residual_power)"},
    ]
    df = pd.DataFrame(rows)
    df.to_csv(cfg.output_dir / "q1_preprocessing_noise_analysis.csv", index=False, encoding="utf-8-sig")
    return df


def plot_noise_analysis(cfg: Config, result: dict[str, float | bool | str]) -> None:
    t, x, _ = load_single_source(cfg.data_path)
    y = preprocess(x)
    s_hat = recovered_signal(t, x, float(result["refined_frequency_hz"]))
    residual = y - s_hat
    zoom_mask = t <= 10.0

    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5))
    axes[0].plot(t[zoom_mask], y[zoom_mask], color="0.65", linewidth=0.8, label="预处理后信号")
    axes[0].plot(t[zoom_mask], residual[zoom_mask], color="tab:blue", linewidth=0.9, label="残差/噪声估计")
    axes[0].set_title("预处理信号与残差噪声估计（前 10 s）")
    axes[0].set_xlabel("时间 (s)")
    axes[0].set_ylabel("幅值")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.25)

    axes[1].hist(residual, bins=80, density=True, color="tab:blue", alpha=0.55, label="残差直方图")
    mu = float(np.mean(residual))
    sigma = float(np.std(residual))
    xs = np.linspace(mu - 4.0 * sigma, mu + 4.0 * sigma, 400)
    axes[1].plot(xs, stats.norm.pdf(xs, mu, sigma), color="tab:red", linewidth=1.4, label="Gaussian 拟合")
    axes[1].set_title("移除拟合正弦分量后的残差分布")
    axes[1].set_xlabel("残差幅值")
    axes[1].set_ylabel("概率密度")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.25)

    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_preprocessing_noise_analysis.png", dpi=180)
    plt.close()


def write_parameter_table(cfg: Config) -> pd.DataFrame:
    rows = [
        {"parameter": "f_min", "value": cfg.f_min, "unit": "Hz", "meaning": "lower bound of frequency search"},
        {"parameter": "f_max", "value": cfg.f_max, "unit": "Hz", "meaning": "upper bound of frequency search"},
        {"parameter": "p_fa", "value": cfg.p_fa, "unit": "-", "meaning": "target false alarm rate"},
        {"parameter": "glrt_mc", "value": cfg.glrt_mc, "unit": "runs", "meaning": "Monte Carlo runs for threshold"},
        {"parameter": "random_seed", "value": cfg.random_seed, "unit": "-", "meaning": "reproducible random seed"},
        {"parameter": "preprocess", "value": "linear detrend", "unit": "-", "meaning": "remove DC and linear trend"},
        {
            "parameter": "refine_half_width",
            "value": "max(3*fs/N, 0.01)",
            "unit": "Hz",
            "meaning": "local frequency refinement window",
        },
        {
            "parameter": "success_tolerance",
            "value": 0.05,
            "unit": "Hz",
            "meaning": "simulation success if frequency error is within this bound",
        },
    ]
    df = pd.DataFrame(rows)
    df.to_csv(cfg.output_dir / "q1_glrt_parameters.csv", index=False, encoding="utf-8-sig")
    return df


def run_segment_validation(cfg: Config, segment_seconds: float = 50.0) -> pd.DataFrame:
    t, x, fs = load_single_source(cfg.data_path)
    segment_len = int(round(segment_seconds * fs))
    rows = []
    for start in range(0, len(x), segment_len):
        end = min(start + segment_len, len(x))
        if end - start < int(10 * fs):
            continue
        seg_t = t[start:end]
        seg_x = x[start:end]
        seg_cfg = Config(**{**cfg.__dict__, "output_dir": cfg.output_dir})
        detected = glrt_detect_signal(seg_t, seg_x, fs, seg_cfg)
        rows.append(
            {
                "segment_id": len(rows) + 1,
                "start_s": float(seg_t[0]),
                "end_s": float(seg_t[-1]),
                "sample_count": len(seg_x),
                "detected": detected["detected"],
                "coarse_frequency_hz": detected["coarse_frequency_hz"],
                "refined_frequency_hz": detected["refined_frequency_hz"],
                "glrt_score": detected["score"],
                "threshold": detected["threshold"],
                "frequency_error_from_2hz": abs(float(detected["refined_frequency_hz"]) - 2.0),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(cfg.output_dir / "q1_segment_validation.csv", index=False, encoding="utf-8-sig")
    return df


def plot_segment_validation(segment_df: pd.DataFrame, cfg: Config) -> None:
    plt.figure(figsize=(10, 4.8))
    plt.plot(segment_df["segment_id"], segment_df["refined_frequency_hz"], marker="o", label="分段估计值")
    plt.axhline(2.0, color="tab:red", linestyle="--", linewidth=1.0, label="2 Hz 参考值")
    plt.xlabel("分段编号")
    plt.ylabel("精修频率 (Hz)")
    plt.title("50 s 分段上的 GLRT 频率估计")
    plt.xticks(segment_df["segment_id"])
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_segment_frequency_validation.png", dpi=180)
    plt.close()


def synthetic_signal(
    fs: float,
    n: int,
    f0: float,
    amplitude: float,
    snr_db: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(n, dtype=float) / fs
    phase = rng.uniform(0.0, 2.0 * np.pi)
    s = amplitude * np.sin(2.0 * np.pi * f0 * t + phase)
    signal_power = float(np.mean(s * s))
    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    x = s + rng.normal(0.0, math.sqrt(noise_power), n)
    return t, x


def run_fft_glrt_simulation(
    cfg: Config,
    f0: float,
    amplitude: float,
    fs: float,
    n: int,
    sim_mc: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.random_seed + 99)
    snr_values = [-25.0, -22.0, -20.0, -18.0, -15.0, -12.0, -10.0, -5.0]
    sim_n = min(n, 12000)
    sim_cfg = Config(**{**cfg.__dict__, "glrt_mc": max(120, min(cfg.glrt_mc, 300))})
    rows = []
    tolerance = 0.05

    for snr_db in snr_values:
        per_method = {
            "FFT peak": {"success": [], "error": []},
            "GLRT": {"success": [], "error": []},
        }
        for _ in range(sim_mc):
            sim_t, sim_x = synthetic_signal(fs, sim_n, f0, amplitude, snr_db, rng)

            fft_res = fft_peak_detect_signal(sim_t, sim_x, fs, sim_cfg)
            fft_error = abs(float(fft_res["refined_frequency_hz"]) - f0)
            per_method["FFT peak"]["success"].append(fft_error <= tolerance)
            per_method["FFT peak"]["error"].append(fft_error)

            glrt_res = glrt_detect_signal(sim_t, sim_x, fs, sim_cfg)
            glrt_error = abs(float(glrt_res["refined_frequency_hz"]) - f0)
            per_method["GLRT"]["success"].append(bool(glrt_res["detected"]) and glrt_error <= tolerance)
            per_method["GLRT"]["error"].append(glrt_error)

        for method, values in per_method.items():
            errors = np.asarray(values["error"], dtype=float)
            rows.append(
                {
                    "method": method,
                    "snr_db": snr_db,
                    "p_detect": float(np.mean(values["success"])),
                    "mean_abs_frequency_error_hz": float(np.mean(errors)),
                    "std_abs_frequency_error_hz": float(np.std(errors)),
                    "mc_runs": sim_mc,
                    "sample_count": sim_n,
                    "success_tolerance_hz": tolerance,
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(cfg.output_dir / "q1_fft_vs_glrt_simulation.csv", index=False, encoding="utf-8-sig")
    return df


def plot_pd_snr(sim_df: pd.DataFrame, cfg: Config) -> None:
    plt.figure(figsize=(9, 5))
    for method, group in sim_df.groupby("method"):
        group = group.sort_values("snr_db")
        label = "FFT 峰值法" if method == "FFT peak" else method
        plt.plot(group["snr_db"], group["p_detect"], marker="o", linewidth=1.8, label=label)
    plt.xlabel("SNR (dB)")
    plt.ylabel("$P_D$")
    plt.title("检测概率 $P_D$ 与 SNR 的关系")
    plt.ylim(-0.03, 1.03)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_pd_snr_curve.png", dpi=180)
    plt.close()


def plot_frequency_error_snr(sim_df: pd.DataFrame, cfg: Config) -> None:
    plt.figure(figsize=(9, 5))
    for method, group in sim_df.groupby("method"):
        group = group.sort_values("snr_db")
        label = "FFT 峰值法" if method == "FFT peak" else method
        plt.plot(group["snr_db"], group["mean_abs_frequency_error_hz"], marker="o", linewidth=1.8, label=label)
    plt.xlabel("SNR (dB)")
    plt.ylabel("平均绝对频率误差 (Hz)")
    plt.title("频率估计误差与 SNR 的关系")
    plt.yscale("log")
    plt.grid(True, alpha=0.3, which="both")
    plt.legend()
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_frequency_error_snr_curve.png", dpi=180)
    plt.close()


def plot_glrt_statistic(cfg: Config, result: dict[str, float | bool | str]) -> None:
    t, x, fs = load_single_source(cfg.data_path)
    freqs, stat = glrt_stat_from_fft(preprocess(x), fs, cfg)
    mask = frequency_bounds(freqs, cfg)
    plot_freqs = freqs[mask]
    plot_stat = stat[mask]
    peak_freq = float(result["refined_frequency_hz"])
    threshold = float(result["threshold"])
    positive_stat = np.maximum(plot_stat, 1e-3)

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), gridspec_kw={"height_ratios": [1.1, 1.0]})

    axes[0].semilogy(plot_freqs, positive_stat, linewidth=0.9, label="GLRT 统计量")
    axes[0].axhline(threshold, color="tab:red", linestyle="--", linewidth=1.0, label="Monte Carlo 阈值")
    axes[0].axvline(peak_freq, color="tab:green", linestyle="--", linewidth=1.0, label="精修 f0")
    axes[0].set_ylabel("统计量（对数）")
    axes[0].set_title("Q1 GLRT 统计量：完整搜索频段")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, alpha=0.25)

    zoom_half_width = 0.25
    zoom_mask = (plot_freqs >= peak_freq - zoom_half_width) & (plot_freqs <= peak_freq + zoom_half_width)
    axes[1].plot(plot_freqs[zoom_mask], plot_stat[zoom_mask], linewidth=1.2, label="GLRT 统计量")
    axes[1].axhline(threshold, color="tab:red", linestyle="--", linewidth=1.0, label="阈值")
    axes[1].axvline(peak_freq, color="tab:green", linestyle="--", linewidth=1.0, label=f"f0 = {peak_freq:.6f} Hz")
    axes[1].set_xlabel("频率 (Hz)")
    axes[1].set_ylabel("统计量")
    axes[1].set_title("峰值附近放大")
    axes[1].legend(fontsize=8)
    axes[1].grid(True, alpha=0.25)

    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_glrt_statistic.png", dpi=180)
    plt.close()


def plot_fft_baseline(cfg: Config, result: dict[str, float | bool | str]) -> None:
    _, x, fs = load_single_source(cfg.data_path)
    freqs, power = fft_spectrum(x, fs)
    mask = frequency_bounds(freqs, cfg)

    plt.figure(figsize=(10, 5))
    plt.semilogy(freqs[mask], power[mask], linewidth=1.0, label="Hann FFT 功率谱")
    plt.axvline(float(result["refined_frequency_hz"]), color="tab:green", linestyle="--", linewidth=1.0, label="GLRT 精修 f0")
    plt.xlabel("频率 (Hz)")
    plt.ylabel("功率（对数）")
    plt.title("Q1 FFT 基线与 GLRT 选定频率")
    plt.legend()
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_glrt_fft_baseline.png", dpi=180)
    plt.close()


def recovered_signal(t: np.ndarray, x: np.ndarray, freq: float) -> np.ndarray:
    y = preprocess(x)
    omega_t = 2.0 * np.pi * freq * t
    design = np.column_stack([np.sin(omega_t), np.cos(omega_t), np.ones_like(t)])
    coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
    return design @ coeffs


def plot_recovered_signal(cfg: Config, result: dict[str, float | bool | str]) -> None:
    t, x, _ = load_single_source(cfg.data_path)
    y = preprocess(x)
    s_hat = recovered_signal(t, x, float(result["refined_frequency_hz"]))

    zoom_seconds = 10.0
    zoom_mask = t <= zoom_seconds

    plt.figure(figsize=(11, 5))
    plt.plot(t[zoom_mask], y[zoom_mask], color="0.65", linewidth=0.9, label="预处理后原始信号")
    plt.plot(t[zoom_mask], s_hat[zoom_mask], color="tab:red", linewidth=1.6, label="GLRT 提取的微弱信号")
    plt.xlabel("时间 (s)")
    plt.ylabel("幅值")
    plt.title("Q1 原始数据与 GLRT 提取微弱信号叠加（前 10 s）")
    plt.legend()
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_glrt_recovered_overlay_zoom.png", dpi=180)
    plt.close()

    plt.figure(figsize=(11, 4.8))
    plt.plot(t[zoom_mask], s_hat[zoom_mask], color="tab:red", linewidth=1.8)
    plt.axhline(0.0, color="0.25", linewidth=0.8)
    plt.xlabel("时间 (s)")
    plt.ylabel("幅值")
    plt.title("GLRT 提取的微弱正弦信号（前 10 s）")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_glrt_recovered_signal_full.png", dpi=180)
    plt.close()


def write_report(
    cfg: Config,
    result: dict[str, float | bool | str],
    noise_df: pd.DataFrame,
    parameter_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    simulation_df: pd.DataFrame,
) -> None:
    row = pd.DataFrame([result])
    row.to_csv(cfg.output_dir / "q1_glrt_result.csv", index=False, encoding="utf-8-sig")

    detected_text = "判定存在显著微弱周期故障信号" if result["detected"] else "未达到显著检测阈值"
    noise_report = noise_df.copy()
    parameter_report = parameter_df.copy()
    segment_report = segment_df.copy()
    simulation_report = simulation_df.copy()

    lines = [
        "# Q1 GLRT 微弱周期信号检测模型",
        "",
        "## 模型选择",
        "",
        "Q1 采用匹配滤波 / 广义似然比检验（GLRT）作为主模型。题面给出的故障信号为单一正弦周期信号，GLRT 与该信号假设直接匹配，并且可以通过 Monte Carlo 阈值控制误报率。",
        "",
        "## 判决结果",
        "",
        f"- 数据源: `{cfg.data_path.name}` / sheet `{SHEET_SINGLE}`",
        f"- 样本数: `{int(result['sample_count'])}`",
        f"- 采样率: `{float(result['sampling_rate_hz']):.6g} Hz`",
        f"- 搜索频率范围: `{cfg.f_min:g} - {cfg.f_max:g} Hz`",
        f"- 目标误报率: `{cfg.p_fa:g}`",
        f"- GLRT 统计量最大值: `{float(result['glrt_score']):.8g}`",
        f"- Monte Carlo 阈值: `{float(result['threshold']):.8g}`",
        f"- 粗估频率: `{float(result['coarse_frequency_hz']):.8g} Hz`",
        f"- 精修频率: `{float(result['refined_frequency_hz']):.10g} Hz`",
        f"- 判决: **{detected_text}**",
        "",
        "## 数学模型与公式",
        "",
        "题面单源故障信号建模为：",
        "",
        "$$x(t)=A\\sin(2\\pi f_0t+\\phi_0)+n(t).$$",
        "",
        "对候选频率 $f$，构造二维正交基：",
        "",
        "$$X_f=[\\sin(2\\pi ft),\\ \\cos(2\\pi ft)].$$",
        "",
        "GLRT 将信号投影到该二维子空间，检测统计量可写成：",
        "",
        "$$T(f)=\\frac{x^TP_fx}{\\hat\\sigma^2},\\quad P_f=X_f(X_f^TX_f)^{-1}X_f^T.$$",
        "",
        "最终判决规则为：",
        "",
        "$$\\max_f T(f)>\\eta_\\alpha,$$",
        "",
        "其中 $\\eta_\\alpha$ 由纯噪声 Monte Carlo 仿真得到，使多频点扫描下的目标误报率满足 $P_{FA}\\le\\alpha$。",
        "",
        "## 流程图",
        "",
        "```mermaid",
        "flowchart TD",
        "    A[读取单源故障数据] --> B[时间轴校验与线性去趋势]",
        "    B --> C[构造候选频率网格]",
        "    C --> D[计算正弦/余弦投影能量]",
        "    D --> E[得到 GLRT 统计量 T(f)]",
        "    E --> F[纯噪声 Monte Carlo 生成阈值]",
        "    E --> G[寻找最大统计量对应频率]",
        "    F --> H{Tmax 是否超过阈值}",
        "    G --> H",
        "    H -->|是| I[判定存在故障频率]",
        "    H -->|否| J[判定无显著故障频率]",
        "    I --> K[最小二乘精修 f0]",
        "    K --> L[输出 f0 与图表]",
        "```",
        "",
        "## 数据预处理与噪声分析",
        "",
        noise_report.to_markdown(index=False, floatfmt=".6g"),
        "",
        "预处理采用线性去趋势。拟合并移除 2 Hz 正弦分量后，残差作为噪声估计；残差偏度和超额峭度用于检查其是否接近高斯白噪声假设。",
        "",
        "## GLRT 参数记录",
        "",
        parameter_report.to_markdown(index=False, floatfmt=".6g"),
        "",
        "## 400 秒数据分段稳定性验证",
        "",
        segment_report.to_markdown(index=False, floatfmt=".6g"),
        "",
        "分段验证用于说明检测结论不是由某个短时异常峰造成。若每个 50 秒段均检出约 2 Hz，则说明故障周期分量在整段观测中稳定存在。",
        "",
        "## FFT 峰值法与 GLRT 仿真对比",
        "",
        simulation_report.to_markdown(index=False, floatfmt=".6g"),
        "",
        "仿真数据按题面模型生成，改变 SNR 后统计检测概率 $P_D$ 与频率误差。FFT 峰值法没有显式误报控制，GLRT 则要求统计量超过 Monte Carlo 阈值且频率误差小于 0.05 Hz。",
        "",
        "## 论文表述要点",
        "",
        "- 对每个候选频率构造正弦/余弦基，将观测信号投影到该二维子空间。",
        "- 投影能量除以噪声方差得到 GLRT 检测统计量；统计量越大，说明该频率处存在周期分量的证据越强。",
        "- 用纯噪声 Monte Carlo 模拟最大统计量分布，并取上分位数作为阈值，从而将多频点扫描下的误报率控制在目标水平。",
        "- 检出后在峰值邻域用最小二乘精修频率，避免 FFT 频率栅格造成的离散化误差。",
        "- 分段验证和 SNR 仿真共同支持该方法在强噪声背景下的稳定性。",
        "",
        "## 第一问结论",
        "",
        f"GLRT 在目标误报率 `{cfg.p_fa:g}` 下给出的统计量 `{float(result['glrt_score']):.6g}` 远高于阈值 `{float(result['threshold']):.6g}`，因此判定单源故障频率显著存在。经最小二乘精修，故障特征频率估计为 `{float(result['refined_frequency_hz']):.10g} Hz`。",
        "",
        "## 输出文件",
        "",
        "- `q1_glrt_result.csv`: Q1 GLRT 数值结果",
        "- `q1_glrt_parameters.csv`: GLRT 参数表",
        "- `q1_preprocessing_noise_analysis.csv`: 预处理与噪声分析",
        "- `q1_segment_validation.csv`: 50 秒分段检测结果",
        "- `q1_fft_vs_glrt_simulation.csv`: 不同 SNR 下 FFT 与 GLRT 对比",
        "- `q1_glrt_statistic.png`: GLRT 统计量曲线与阈值",
        "- `q1_glrt_fft_baseline.png`: FFT 基线频谱与 GLRT 选定频率",
        "- `q1_glrt_recovered_overlay_zoom.png`: 原始信号与 GLRT 提取弱信号叠加图",
        "- `q1_glrt_recovered_signal_full.png`: GLRT 提取弱信号全时段图",
        "- `q1_preprocessing_noise_analysis.png`: 预处理与残差噪声图",
        "- `q1_segment_frequency_validation.png`: 分段频率估计图",
        "- `q1_pd_snr_curve.png`: 检测概率-SNR 曲线",
        "- `q1_frequency_error_snr_curve.png`: 频率误差-SNR 曲线",
        "",
    ]
    (cfg.output_dir / "q1_glrt_report.md").write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the selected Q1 GLRT model.")
    parser.add_argument("--data", type=Path, default=Path("data.xlsx"))
    parser.add_argument("--output-dir", type=Path, default=Path("q1_glrt_results"))
    parser.add_argument("--glrt-mc", type=int, default=500)
    parser.add_argument("--p-fa", type=float, default=0.05)
    parser.add_argument("--f-min", type=float, default=0.05)
    parser.add_argument("--f-max", type=float, default=49.5)
    parser.add_argument("--sim-mc", type=int, default=80)
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
    parameter_df = write_parameter_table(cfg)
    segment_df = run_segment_validation(cfg, segment_seconds=args.segment_seconds)
    simulation_df = run_fft_glrt_simulation(
        cfg,
        f0=float(result["refined_frequency_hz"]),
        amplitude=float(result["amplitude_for_reference"]),
        fs=float(result["sampling_rate_hz"]),
        n=int(result["sample_count"]),
        sim_mc=args.sim_mc,
    )
    write_report(cfg, result, noise_df, parameter_df, segment_df, simulation_df)
    plot_glrt_statistic(cfg, result)
    plot_fft_baseline(cfg, result)
    plot_recovered_signal(cfg, result)
    plot_noise_analysis(cfg, result)
    plot_segment_validation(segment_df, cfg)
    plot_pd_snr(simulation_df, cfg)
    plot_frequency_error_snr(simulation_df, cfg)

    print("Q1 GLRT result")
    for key, value in result.items():
        print(f"{key}: {value}")
    print(f"\nWrote outputs to: {cfg.output_dir.resolve()}")


if __name__ == "__main__":
    main()
