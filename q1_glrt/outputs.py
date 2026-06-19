"""File and figure generation for the Q1 GLRT model."""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from scipy import stats

from q1_glrt.core import load_q1_data, recovered_signal, require_frequency_mask
from q1_model_compare import (
    Config,
    SHEET_SINGLE,
    fft_spectrum,
    glrt_stat_from_fft,
    preprocess,
)


def configure_plot_fonts() -> None:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ["Microsoft YaHei", "SimHei", "SimSun"]:
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def write_csv_outputs(
    cfg: Config,
    result: dict[str, float | bool | str],
    noise_df: pd.DataFrame,
    parameter_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    simulation_df: pd.DataFrame,
) -> None:
    pd.DataFrame([result]).to_csv(cfg.output_dir / "q1_glrt_result.csv", index=False, encoding="utf-8-sig")
    noise_df.to_csv(cfg.output_dir / "q1_preprocessing_noise_analysis.csv", index=False, encoding="utf-8-sig")
    parameter_df.to_csv(cfg.output_dir / "q1_glrt_parameters.csv", index=False, encoding="utf-8-sig")
    segment_df.to_csv(cfg.output_dir / "q1_segment_validation.csv", index=False, encoding="utf-8-sig")
    simulation_df.to_csv(cfg.output_dir / "q1_fft_vs_glrt_simulation.csv", index=False, encoding="utf-8-sig")


def plot_noise_analysis(cfg: Config, result: dict[str, float | bool | str]) -> None:
    t, x, _ = load_q1_data(cfg)
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
    _, x, fs = load_q1_data(cfg)
    freqs, stat = glrt_stat_from_fft(x, fs, cfg)
    mask = require_frequency_mask(freqs, cfg)
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
    _, x, fs = load_q1_data(cfg)
    freqs, power = fft_spectrum(x, fs)
    mask = require_frequency_mask(freqs, cfg)

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


def plot_recovered_signal(cfg: Config, result: dict[str, float | bool | str]) -> None:
    t, x, _ = load_q1_data(cfg)
    y = preprocess(x)
    s_hat = recovered_signal(t, x, float(result["refined_frequency_hz"]))
    zoom_mask = t <= 10.0

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
    detected_text = "判定存在显著微弱周期故障信号" if result["detected"] else "未达到显著检测阈值"
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
        noise_df.to_markdown(index=False, floatfmt=".6g"),
        "",
        "预处理采用线性去趋势。拟合并移除 2 Hz 正弦分量后，残差作为噪声估计；残差偏度和超额峰度用于检查其是否接近 Gaussian 白噪声假设。",
        "",
        "## GLRT 参数记录",
        "",
        parameter_df.to_markdown(index=False, floatfmt=".6g"),
        "",
        "## 400 秒数据分段稳定性验证",
        "",
        segment_df.to_markdown(index=False, floatfmt=".6g"),
        "",
        "分段验证用于说明检测结论不是由某个短时异常峰造成。若每个 50 秒段均检出约 2 Hz，则说明故障周期分量在整段观测中稳定存在。",
        "",
        "## FFT 峰值法与 GLRT 仿真对比",
        "",
        simulation_df.to_markdown(index=False, floatfmt=".6g"),
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
        "- `q1_glrt_recovered_signal_full.png`: GLRT 提取弱信号图",
        "- `q1_preprocessing_noise_analysis.png`: 预处理与残差噪声图",
        "- `q1_segment_frequency_validation.png`: 分段频率估计图",
        "- `q1_pd_snr_curve.png`: 检测概率-SNR 曲线",
        "- `q1_frequency_error_snr_curve.png`: 频率误差-SNR 曲线",
        "",
    ]
    (cfg.output_dir / "q1_glrt_report.md").write_text("\n".join(lines), encoding="utf-8")


def write_all_outputs(
    cfg: Config,
    result: dict[str, float | bool | str],
    noise_df: pd.DataFrame,
    parameter_df: pd.DataFrame,
    segment_df: pd.DataFrame,
    simulation_df: pd.DataFrame,
) -> None:
    write_csv_outputs(cfg, result, noise_df, parameter_df, segment_df, simulation_df)
    write_report(cfg, result, noise_df, parameter_df, segment_df, simulation_df)
    plot_glrt_statistic(cfg, result)
    plot_fft_baseline(cfg, result)
    plot_recovered_signal(cfg, result)
    plot_noise_analysis(cfg, result)
    plot_segment_validation(segment_df, cfg)
    plot_pd_snr(simulation_df, cfg)
    plot_frequency_error_snr(simulation_df, cfg)
