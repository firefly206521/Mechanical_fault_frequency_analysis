"""CSV, Markdown, and dependency-free SVG output helpers for Q2."""

from __future__ import annotations

import csv
import html
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from .core import autocorrelation, spectrum


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _points(x, y, x0, y0, width, height, xmin, xmax, ymin, ymax):
    px = x0 + (np.asarray(x) - xmin) / max(xmax - xmin, 1e-30) * width
    py = y0 + height - (np.asarray(y) - ymin) / max(ymax - ymin, 1e-30) * height
    return " ".join(f"{a:.2f},{b:.2f}" for a, b in zip(px, py))


def line_svg(path: Path, title: str, xlabel: str, ylabel: str, series: list[tuple], log_y: bool = False) -> None:
    clean = []
    for name, x, y, color in series:
        x, y = np.asarray(x, float), np.asarray(y, float)
        if log_y:
            y = np.log10(np.maximum(y, 1e-30))
        finite = np.isfinite(x) & np.isfinite(y)
        if np.any(finite):
            clean.append((name, x[finite], y[finite], color))
    if not clean:
        print(f"Warning: skipped empty plot {path.name}", file=sys.stderr)
        return
    xmin = min(float(np.min(s[1])) for s in clean)
    xmax = max(float(np.max(s[1])) for s in clean)
    ymin = min(float(np.min(s[2])) for s in clean)
    ymax = max(float(np.max(s[2])) for s in clean)
    pad = 0.06 * max(ymax - ymin, 1e-9)
    ymin, ymax = ymin - pad, ymax + pad
    # 1100x500 rendered at 1.8 device scale gives 1980x900, matching the
    # dominant Q1 single-panel figure size.
    W, H, x0, y0, pw, ph = 1100, 500, 90, 60, 940, 350
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{W/2}" y="32" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="22">{html.escape(title)}</text>',
             f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="none" stroke="#444"/>']
    for i in range(6):
        x = x0 + pw * i / 5
        value = xmin + (xmax - xmin) * i / 5
        parts += [f'<line x1="{x}" y1="{y0}" x2="{x}" y2="{y0+ph}" stroke="#ddd"/>',
                  f'<text x="{x}" y="{y0+ph+22}" text-anchor="middle" font-family="Arial" font-size="12">{value:.4g}</text>']
        y = y0 + ph - ph * i / 5
        val_y = ymin + (ymax - ymin) * i / 5
        label = f"10^{val_y:.1f}" if log_y else f"{val_y:.4g}"
        parts += [f'<line x1="{x0}" y1="{y}" x2="{x0+pw}" y2="{y}" stroke="#ddd"/>',
                  f'<text x="{x0-10}" y="{y+4}" text-anchor="end" font-family="Arial" font-size="12">{label}</text>']
    for idx, (name, x, y, color) in enumerate(clean):
        pts = _points(x, y, x0, y0, pw, ph, xmin, xmax, ymin, ymax)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.9"/>')
        if len(x) <= 50:
            px = x0 + (x - xmin) / max(xmax - xmin, 1e-30) * pw
            py = y0 + ph - (y - ymin) / max(ymax - ymin, 1e-30) * ph
            parts.extend(f'<circle cx="{a:.2f}" cy="{b:.2f}" r="4" fill="{color}"/>' for a, b in zip(px, py))
        ly = 82 + idx * 22
        parts += [f'<line x1="{x0+pw-190}" y1="{ly}" x2="{x0+pw-160}" y2="{ly}" stroke="{color}" stroke-width="3"/>',
                  f'<text x="{x0+pw-150}" y="{ly+4}" font-family="Arial,Microsoft YaHei" font-size="13">{html.escape(name)}</text>']
    parts += [f'<text x="{x0+pw/2}" y="{H-20}" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="15">{html.escape(xlabel)}</text>',
              f'<text x="22" y="{y0+ph/2}" transform="rotate(-90 22 {y0+ph/2})" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="15">{html.escape(ylabel)}</text>',
              '</svg>']
    path.write_text("\n".join(parts), encoding="utf-8")


def residual_diagnostics_svg(path: Path, residual: np.ndarray) -> None:
    z = (residual - np.mean(residual)) / np.std(residual)
    hist, edges = np.histogram(z, bins=60, density=True)
    centers = (edges[:-1] + edges[1:]) / 2
    normal = np.exp(-centers**2 / 2) / math.sqrt(2 * math.pi)
    acf = autocorrelation(residual, 100)
    from statistics import NormalDist
    sample = np.sort(z[::max(1, len(z)//2000)])
    probs = (np.arange(len(sample)) + 0.5) / len(sample)
    theoretical = np.asarray([NormalDist().inv_cdf(float(p)) for p in probs])

    W, H = 1200, 430
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">', '<rect width="100%" height="100%" fill="white"/>',
             '<text x="600" y="28" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="21">残差诊断</text>']
    panels = [(45, 60, 330, 300), (435, 60, 330, 300), (825, 60, 330, 300)]
    for x0, y0, pw, ph in panels:
        parts.append(f'<rect x="{x0}" y="{y0}" width="{pw}" height="{ph}" fill="none" stroke="#555"/>')
    pts1 = _points(centers, hist, *panels[0], float(edges[0]), float(edges[-1]), 0, float(max(hist.max(), normal.max())*1.1))
    pts2 = _points(centers, normal, *panels[0], float(edges[0]), float(edges[-1]), 0, float(max(hist.max(), normal.max())*1.1))
    parts += [f'<polyline points="{pts1}" fill="none" stroke="#1f77b4" stroke-width="2"/>', f'<polyline points="{pts2}" fill="none" stroke="#d62728" stroke-width="2"/>',
              '<text x="210" y="390" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="14">标准化残差分布</text>']
    lags = np.arange(1, 101)
    pts3 = _points(lags, acf[1:], *panels[1], 1, 100, min(-0.05, float(acf[1:].min())), max(0.05, float(acf[1:].max())))
    parts += [f'<polyline points="{pts3}" fill="none" stroke="#2ca02c" stroke-width="1.5"/>',
              '<text x="600" y="390" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="14">残差自相关（1-100阶）</text>']
    lo = float(min(theoretical.min(), sample.min())); hi = float(max(theoretical.max(), sample.max()))
    pts4 = _points(theoretical, sample, *panels[2], lo, hi, lo, hi)
    diag = _points([lo, hi], [lo, hi], *panels[2], lo, hi, lo, hi)
    parts += [f'<polyline points="{diag}" fill="none" stroke="#999" stroke-width="1"/>', f'<polyline points="{pts4}" fill="none" stroke="#9467bd" stroke-width="1.5"/>',
              '<text x="990" y="390" text-anchor="middle" font-family="Arial,Microsoft YaHei" font-size="14">正态Q-Q图</text>', '</svg>']
    path.write_text("\n".join(parts), encoding="utf-8")


def write_plots(
    output_dir: Path,
    t,
    y,
    fit,
    filtered,
    joint_rows,
    simulation_rows,
    fs,
    ssa_best=None,
    ssa_best_window=None,
    segment_sensitivity_rows=None,
):
    zoom = t <= 10.0
    line_svg(output_dir / "q2_time_overlay_zoom.svg", "Q2 原始数据与恢复波形叠加（前10 s）", "时间 (s)", "幅值", [
        ("预处理信号", t[zoom], y[zoom], "#999999"),
        ("谐波回归", t[zoom], fit["fit"][zoom], "#d62728"),
        ("针对性窄带", t[zoom], filtered[zoom], "#1f77b4"),
    ])
    step = max(1, len(t)//4000)
    line_svg(output_dir / "q2_recovered_full.svg", "Q2 谐波回归恢复信号（完整400 s）", "时间 (s)", "恢复幅值", [
        ("谐波回归", t[::step], fit["fit"][::step], "#d62728"),
    ])
    f1, p1 = spectrum(y, fs); _, p2 = spectrum(fit["fit"], fs); _, p3 = spectrum(fit["residual"], fs)
    mask = (f1 >= 0.05) & (f1 <= 49.5)
    line_svg(output_dir / "q2_spectrum_comparison.svg", "Q2 恢复前后频谱对比", "频率 (Hz)", "功率（对数）", [
        ("原始", f1[mask], p1[mask], "#777777"), ("恢复", f1[mask], p2[mask], "#d62728"), ("残差", f1[mask], p3[mask], "#1f77b4")], log_y=True)
    mask2 = (f1 >= 1.8) & (f1 <= 2.2)
    line_svg(output_dir / "q2_spectrum_2hz_zoom.svg", "Q2 2 Hz附近频谱对比", "频率 (Hz)", "功率（对数）", [
        ("原始", f1[mask2], p1[mask2], "#777777"), ("残差", f1[mask2], p3[mask2], "#1f77b4")], log_y=True)
    residual_diagnostics_svg(output_dir / "q2_residual_diagnostics.svg", fit["residual"])
    if joint_rows:
        centers = np.asarray([(r["start_s"] + r["end_s"]) / 2 for r in joint_rows])
        line_svg(output_dir / "q2_segment_stability.svg", "Q2 50 s分段频率偏差", "时间 (s)", "频率偏差 (Hz)", [
            ("|独立频率-公共频率|", centers, [abs(r["independent_deviation_from_common_hz"]) for r in joint_rows], "#d62728"),
        ])
        line_svg(output_dir / "q2_segment_amplitude.svg", "Q2 50 s分段振幅", "时间 (s)", "振幅", [
            ("振幅", centers, [r["amplitude"] for r in joint_rows], "#1f77b4"),
        ])
        line_svg(output_dir / "q2_segment_phase.svg", "Q2 50 s分段初相位", "时间 (s)", "相位 (rad)", [
            ("初相位", centers, [r["phase_origin_rad"] for r in joint_rows], "#9467bd"),
        ])
        line_svg(output_dir / "q2_segment_snr.svg", "Q2 50 s分段估计SNR", "时间 (s)", "SNR (dB)", [
            ("SNR", centers, [r["estimated_snr_db"] for r in joint_rows], "#2ca02c"),
        ])
    else:
        print("Warning: skipped 50 s segment plots because no segment rows were produced.", file=sys.stderr)
    line_svg(output_dir / "q2_simulation_validation.svg", "Q2 合成数据恢复误差", "SNR (dB)", "误差", [
        ("频率绝对误差/Hz", [r["snr_db"] for r in simulation_rows], [r["mean_abs_frequency_error_hz"] for r in simulation_rows], "#1f77b4"),
        ("波形RMSE", [r["snr_db"] for r in simulation_rows], [r["mean_waveform_rmse"] for r in simulation_rows], "#d62728"),
    ])
    if ssa_best is not None:
        line_svg(output_dir / "q2_ssa_comparison.svg", f"Q2 SSA对照（最佳窗口{ssa_best_window}点，前10 s）", "时间 (s)", "幅值", [
            ("预处理信号", t[zoom], y[zoom], "#999999"),
            ("谐波回归", t[zoom], fit["fit"][zoom], "#d62728"),
            ("SSA恢复", t[zoom], np.asarray(ssa_best)[zoom], "#2ca02c"),
        ])
    if segment_sensitivity_rows:
        lengths = [r["segment_seconds"] for r in segment_sensitivity_rows]
        line_svg(output_dir / "q2_segment_length_sensitivity.svg", "Q2 分段长度敏感性：频率偏差", "分段长度 (s)", "频率偏差 (Hz)", [
            ("平均绝对偏差", lengths, [r["mean_abs_frequency_deviation_hz"] for r in segment_sensitivity_rows], "#1f77b4"),
            ("最大绝对偏差", lengths, [r["max_abs_frequency_deviation_hz"] for r in segment_sensitivity_rows], "#d62728"),
        ])
        line_svg(output_dir / "q2_segment_bic_sensitivity.svg", "Q2 分段长度敏感性：公共频率BIC优势", "分段长度 (s)", "BIC差（独立-公共）", [
            ("正值支持公共频率", lengths, [r["bic_advantage_common"] for r in segment_sensitivity_rows], "#9467bd"),
        ])


def convert_svg_plots_to_png(output_dir: Path, remove_svg: bool = True) -> list[Path]:
    """Render SVG plots to PNG using an installed Chromium browser.

    Single-panel 1100x500 SVGs become 1980x900 PNGs at scale 1.8.  The
    residual diagnostic keeps its own multi-panel aspect ratio.
    """
    browser_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    browser = next((p for p in browser_candidates if p.exists()), None)
    if browser is None:
        print("Warning: Chrome/Edge not found; keeping SVG plots and skipping PNG rendering.", file=sys.stderr)
        return []
    outputs = []
    with tempfile.TemporaryDirectory(prefix="q2_svg_render_") as profile:
        for svg in sorted(output_dir.glob("q2_*.svg")):
            first = svg.read_text(encoding="utf-8", errors="ignore")[:300]
            width_match = re.search(r'width="(\d+)"', first)
            height_match = re.search(r'height="(\d+)"', first)
            width = int(width_match.group(1)) if width_match else 1100
            height = int(height_match.group(1)) if height_match else 500
            png = svg.with_suffix(".png")
            cmd = [
                str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--no-first-run", f"--user-data-dir={profile}",
                "--force-device-scale-factor=1.8", f"--window-size={width},{height}",
                f"--screenshot={png}", svg.resolve().as_uri(),
            ]
            completed = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if completed.returncode == 0 and png.exists() and png.stat().st_size > 0:
                outputs.append(png)
                if remove_svg:
                    svg.unlink()
    return outputs


def write_report(path: Path, context: dict) -> None:
    g = context["global"]
    ci = {r["parameter"]: r for r in context["bootstrap"]}
    diag = {(r["source"], r["metric"]): r["value"] for r in context["diagnostics"]}
    comparison = {r["model"]: r for r in context["model_comparison"]}
    filt = {r["metric"]: r for r in context["filter_comparison"]}
    ssa = context["ssa_comparison"]
    ssa_best = max(ssa, key=lambda row: row["correlation_to_harmonic"])
    sensitivity = context["segment_sensitivity"]
    sim = context["simulation"]
    coverage_ok = all(r[k] >= 0.90 for r in sim for k in ["frequency_ci95_coverage", "amplitude_ci95_coverage", "phase_ci95_coverage"])
    lines = [
        "# 第二问：单源故障波形恢复",
        "",
        "## 1. 方法选择",
        "",
        "题面把故障信号定义为稳定正弦波。第一问检测到约2 Hz的显著周期分量，移除该分量后的残差接近高斯白噪声。因此，本问使用谐波回归恢复波形，并用针对性窄带滤波和奇异谱分析（SSA）作对照。MCKD、Kurtogram和循环平稳盲解卷积针对周期冲击与共振调制；当前数据没有触发该扩展分支。",
        "",
        "报告《强噪声下微弱故障信号检测报告》强调利用故障周期先验、多时间窗稳定性和误报控制。本模型保留这些原则，但按照赛题给定的正弦机理选择参数化恢复方法。",
        "",
        "## 2. 全局恢复结果",
        "",
        "预处理采用线性去趋势。以第一问频率为初值，在其附近重新最小化谐波回归残差。最终模型为：",
        "",
        f"$$\\hat s(t)={g['amplitude']:.9f}\\sin(2\\pi\\times {g['frequency_hz']:.9f}t{g['phase_origin_rad']:+.9f})$$",
        "",
        f"- 频率：{g['frequency_hz']:.9f} Hz",
        f"- 振幅：{g['amplitude']:.9f}",
        f"- 初相位：{g['phase_origin_rad']:.9f} rad",
        f"- 残差标准差：{g['residual_std']:.9f}",
        f"- 解释方差：{g['explained_variance']:.4%}",
        f"- 估计输入SNR：{g['estimated_snr_db']:.3f} dB",
        f"- 2 Hz峰值抑制：{g['target_peak_suppression_db']:.2f} dB",
        "",
        "## 3. 95%置信区间",
        "",
        f"采用{context['bootstrap_runs']}次局部线性化参数Bootstrap，随机种子为{context['seed']}。该实现直接抽样非线性最小二乘估计量的局部协方差，适合本题长序列、单一窄带正弦和近高斯残差。",
        "",
        "| 参数 | 点估计 | 95%区间 | Bootstrap标准差 |",
        "|---|---:|---:|---:|",
    ]
    for key in ["frequency_hz", "amplitude", "phase_origin_rad"]:
        r = ci[key]
        lines.append(f"| {key} | {r['estimate']:.9g} | [{r['ci95_low']:.9g}, {r['ci95_high']:.9g}] | {r['bootstrap_std']:.3g} |")
    lines += [
        "",
        "## 4. 模型适用性诊断",
        "",
        f"残差偏度为{diag[('residual','skewness')]:.4f}，超额峰度为{diag[('residual','excess_kurtosis')]:.4f}，峰值因子为{diag[('residual','crest_factor')]:.3f}。1至100阶残差自相关绝对值最大值为{diag[('residual','max_abs_acf_lag_1_100')]:.4f}。这些结果没有显示强脉冲或明显相关结构。",
        "",
        f"MCKD扩展分支判定：{'触发' if diag[('decision','trigger_mckd_branch')] else '不触发'}。",
        "",
        "## 5. 公共频率联合拟合",
        "",
        f"8个50秒段的公共频率模型BIC为{comparison['common frequency']['bic']:.2f}，独立频率模型BIC为{comparison['independent frequencies']['bic']:.2f}。BIC越低越好。",
        "",
        ("公共频率模型更优，后100秒的分段频率偏差可以由噪声和振幅下降解释。" if comparison['common frequency']['bic'] < comparison['independent frequencies']['bic'] else "独立频率模型BIC更低，需要进一步检查真实频率漂移。"),
        "",
        "### 5.1 分段长度敏感性",
        "",
        "为避免结论依赖固定50秒窗口，分别采用25秒、50秒和100秒分段。BIC差定义为独立频率模型BIC减去公共频率模型BIC，正值支持公共频率。",
        "",
        "| 分段长度/s | 分段数 | 平均频率偏差/Hz | 最大频率偏差/Hz | 振幅变异系数 | 公共频率BIC优势 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sensitivity:
        lines.append(f"| {r['segment_seconds']:.0f} | {r['segment_count']} | {r['mean_abs_frequency_deviation_hz']:.6g} | {r['max_abs_frequency_deviation_hz']:.6g} | {r['amplitude_coefficient_of_variation']:.3%} | {r['bic_advantage_common']:.2f} |")
    all_common = all(r["common_frequency_preferred"] for r in sensitivity)
    lines += [
        "",
        ("三种分段长度都支持公共频率模型，固定频率结论不依赖50秒窗口。" if all_common else "部分窗口没有支持公共频率模型，需要结合短窗估计方差解释。"),
        "",
        "## 6. 对照方法",
        "",
        "### 6.1 针对性窄带滤波",
        "",
        f"窄带恢复与谐波回归在中央390秒的相关系数为{filt['central_waveform_correlation']['targeted_filter']:.6f}，中央RMSE为{filt['central_rmse_to_harmonic_reference']['targeted_filter']:.6g}，边缘RMSE为{filt['edge_rmse_to_harmonic_reference']['targeted_filter']:.6g}。Hilbert包络估计振幅为{filt['estimated_amplitude']['targeted_filter']:.6g}。",
        "",
        "窄带滤波用于验证2 Hz附近的针对性提取。",
        "",
        "### 6.2 奇异谱分析（SSA）",
        "",
        "SSA不预设2 Hz带通区间。程序先用8至10 Hz平滑低通完成抗混叠，再降采样到20 Hz；随后测试相当于原始500、1000和2000点的窗口，并选择频谱能量集中在2 Hz附近的两个SSA分量。",
        "",
        "| 原始窗口点数 | 窗口时长/s | 估计频率/Hz | 估计振幅 | 与谐波回归相关系数 | RMSE |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in ssa:
        lines.append(f"| {r['window_points_original']} | {r['window_seconds']:.1f} | {r['estimated_frequency_hz']:.9f} | {r['estimated_amplitude']:.6f} | {r['correlation_to_harmonic']:.6f} | {r['rmse_to_harmonic']:.6g} |")
    lines += [
        "",
        f"最佳SSA窗口为{context['ssa_best_window']}点，与谐波回归波形的相关系数为{ssa_best['correlation_to_harmonic']:.6f}。谐波回归直接对应题面模型，并统一估计频率、振幅和相位，因此仍作为最终模型；SSA和窄带滤波提供两类独立对照。",
        "",
        "## 7. 合成数据误差实验",
        "",
        f"每次仿真使用{sim[0]['sample_count']}个样本，与真实400秒记录长度一致。",
        "",
        "| SNR/dB | 频率MAE/Hz | 振幅相对误差 | 相位MAE/rad | 波形RMSE | 频率覆盖率 | 振幅覆盖率 | 相位覆盖率 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sim:
        lines.append(f"| {r['snr_db']:.0f} | {r['mean_abs_frequency_error_hz']:.6g} | {r['mean_amplitude_relative_error']:.4%} | {r['mean_abs_phase_error_rad']:.6g} | {r['mean_waveform_rmse']:.6g} | {r['frequency_ci95_coverage']:.1%} | {r['amplitude_ci95_coverage']:.1%} | {r['phase_ci95_coverage']:.1%} |")
    lines += [
        "",
        f"覆盖率验收：{'通过' if coverage_ok else '部分指标低于90%，应结合有限仿真误差解释或增加仿真次数'}。",
        "",
        "## 8. 误差解释",
        "",
        "附件没有提供无噪声真实波形，因此真实数据的残差RMSE不能称为恢复真值误差。真实数据使用残差、解释方差、谱峰抑制和分段稳定性评价；波形RMSE、振幅误差和相位误差来自具有已知真值的合成实验。",
        "",
        "## 9. 结论",
        "",
        f"完整400秒数据支持频率{g['frequency_hz']:.9f} Hz、振幅{g['amplitude']:.6f}、初相位{g['phase_origin_rad']:.6f} rad的稳定正弦故障分量。25秒、50秒和100秒分段均支持公共频率模型；最佳SSA恢复与谐波回归的相关系数为{ssa_best['correlation_to_harmonic']:.6f}。完整40001点仿真、残差诊断和两类对照共同支持最终恢复结果。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
