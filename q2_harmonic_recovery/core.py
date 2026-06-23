"""Numerical routines for Q2 harmonic waveform recovery.

This module intentionally does not import or modify the Q1 package.  It follows
the same detrend + least-squares refinement conventions while remaining
runnable with the bundled NumPy/OpenPyXL runtime.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import openpyxl


def load_single_source(path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["单源故障"]
    rows = [(r[0], r[1]) for r in ws.iter_rows(min_row=2, values_only=True)]
    wb.close()
    try:
        arr = np.asarray(rows, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} sheet '单源故障' must contain only numeric time and signal values.") from exc
    finite = np.isfinite(arr)
    if arr.ndim != 2 or arr.shape[1] != 2 or not bool(np.all(finite)):
        bad = np.argwhere(~finite)
        if len(bad):
            row, col = bad[0]
            cell = f"{'AB'[col]}{row + 2}"
            raise ValueError(f"{path} sheet '单源故障' contains non-finite data at {cell}.")
        raise ValueError(f"{path} sheet '单源故障' must contain exactly two numeric columns.")
    t, x = arr[:, 0], arr[:, 1]
    fs = float(1.0 / np.median(np.diff(t)))
    return t, x, fs


def linear_detrend(t: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tc = t - np.mean(t)
    design = np.column_stack([tc, np.ones_like(tc)])
    coef = np.linalg.lstsq(design, x, rcond=None)[0]
    return x - design @ coef, coef


def wrap_phase(value: np.ndarray | float) -> np.ndarray | float:
    return np.angle(np.exp(1j * value))


def align_phase_to_reference(value: np.ndarray | float, reference: float) -> np.ndarray | float:
    """Move wrapped phase values onto the continuous branch around reference."""
    return reference + wrap_phase(np.asarray(value) - reference)


def phase_in_circular_ci(value: float, center: float, half_width: float) -> bool:
    """Check whether a wrapped phase value lies inside a circular CI."""
    # [AI-1] 辅助实现相位圆周区间判断，代替直接对 wrapped phase 取分位数
    if half_width >= math.pi:
        return True
    value_wrapped = float(wrap_phase(value))
    center_wrapped = float(wrap_phase(center))
    low = center_wrapped - half_width
    high = center_wrapped + half_width
    if low < -math.pi:
        return value_wrapped >= low + 2.0 * math.pi or value_wrapped <= high
    if high > math.pi:
        return value_wrapped >= low or value_wrapped <= high - 2.0 * math.pi
    return low <= value_wrapped <= high


def harmonic_fit(t: np.ndarray, y: np.ndarray, frequency: float) -> dict:
    """谐波回归：以时间中心化后的 sin/cos/offset 做最小二乘，返回振幅、相位、SSE。"""
    # [AI-1] 辅助时间中心化数值稳定设计
    center = float(np.mean(t))
    tc = t - center
    angle = 2.0 * np.pi * frequency * tc
    design = np.column_stack([np.sin(angle), np.cos(angle), np.ones_like(t)])  # [AI-1] 辅助向量化设计矩阵
    beta = np.linalg.lstsq(design, y, rcond=None)[0]
    fit = design @ beta
    residual = y - fit
    a, b, offset = map(float, beta)
    amplitude = float(np.hypot(a, b))
    phase_center = float(math.atan2(b, a))
    phase_origin = float(wrap_phase(phase_center - 2.0 * np.pi * frequency * center))  # [AI-1] 辅助还原相位至 t=0 原点
    return {
        "frequency_hz": float(frequency),
        "a_centered": a,
        "b_centered": b,
        "offset": offset,
        "amplitude": amplitude,
        "phase_center_rad": phase_center,
        "phase_origin_rad": phase_origin,
        "center_time_s": center,
        "fit": fit,
        "residual": residual,
        "sse": float(np.dot(residual, residual)),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "explained_variance": float(1.0 - np.var(residual) / np.var(y)),
    }


def golden_minimize(func, lo: float, hi: float, iterations: int = 55) -> float:
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = hi - ratio * (hi - lo)
    d = lo + ratio * (hi - lo)
    fc, fd = func(c), func(d)
    for _ in range(iterations):
        if fc <= fd:
            hi, d, fd = d, c, fc
            c = hi - ratio * (hi - lo)
            fc = func(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + ratio * (hi - lo)
            fd = func(d)
    return float((lo + hi) / 2.0)


def refine_frequency(t: np.ndarray, y: np.ndarray, initial: float, half_width: float = 0.01) -> dict:
    """黄金分割精修：在初值 ±half_width 内最小化 SSE，无 scipy 依赖。"""
    # [AI-1] 辅助 golden-section 无导搜索替代 scipy 优化器
    frequency = golden_minimize(
        lambda f: harmonic_fit(t, y, f)["sse"],
        max(0.001, initial - half_width),  # [AI-1] 辅助搜索下界裁剪至正频率
        initial + half_width,
    )
    return harmonic_fit(t, y, frequency)


def moment_metrics(x: np.ndarray) -> dict[str, float]:
    centered = x - np.mean(x)
    std = float(np.std(centered))
    z = centered / max(std, np.finfo(float).eps)
    skew = float(np.mean(z**3))
    excess = float(np.mean(z**4) - 3.0)
    rms = float(np.sqrt(np.mean(x**2)))
    crest = float(np.max(np.abs(x)) / max(rms, np.finfo(float).eps))
    jb = float(len(x) / 6.0 * (skew**2 + excess**2 / 4.0))
    jb_p = float(math.exp(-jb / 2.0))  # chi-square(df=2) survival function
    return {
        "mean": float(np.mean(x)),
        "std": std,
        "skewness": skew,
        "excess_kurtosis": excess,
        "raw_kurtosis": excess + 3.0,
        "crest_factor": crest,
        "jarque_bera": jb,
        "jarque_bera_p_approx": jb_p,
    }


def autocorrelation(x: np.ndarray, max_lag: int = 200) -> np.ndarray:
    y = x - np.mean(x)
    denom = float(np.dot(y, y))
    return np.asarray([
        1.0 if lag == 0 else float(np.dot(y[:-lag], y[lag:]) / denom)
        for lag in range(max_lag + 1)
    ])


def spectrum(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    y = x - np.mean(x)
    spec = np.fft.rfft(y * np.hanning(len(y)))
    freq = np.fft.rfftfreq(len(y), 1.0 / fs)
    return freq, np.abs(spec) ** 2


def band_power_rows(x: np.ndarray, fs: float) -> list[dict]:
    freq, power = spectrum(x, fs)
    total = float(np.sum(power[(freq >= 0.05) & (freq <= 49.5)]))
    rows = []
    for lo, hi in [(0.05, 1.0), (1.0, 3.0), (3.0, 10.0), (10.0, 25.0), (25.0, 49.5)]:
        value = float(np.sum(power[(freq >= lo) & (freq < hi)]))
        rows.append({"band_low_hz": lo, "band_high_hz": hi, "power_fraction": value / total})
    return rows


def model_applicability(t: np.ndarray, raw: np.ndarray, y: np.ndarray, fit: dict, fs: float) -> tuple[list[dict], list[dict]]:
    """残差诊断：统计矩、自相关、谱峰抑制、MCKD 触发判定。"""
    # [AI-1] 辅助残差统计矩与谱诊断管线设计
    residual = fit["residual"]
    raw_m = moment_metrics(raw)
    residual_m = moment_metrics(residual)
    acf = autocorrelation(residual, 200)
    freq, p_y = spectrum(y, fs)
    _, p_r = spectrum(residual, fs)
    target_idx = int(np.argmin(np.abs(freq - fit["frequency_hz"])))
    target_suppression_db = float(10.0 * np.log10((p_y[target_idx] + 1e-30) / (p_r[target_idx] + 1e-30)))
    side_mask = (freq >= 1.5) & (freq <= 2.5) & (np.abs(freq - fit["frequency_hz"]) >= 0.03)
    side_ratio = float(np.max(p_y[side_mask]) / np.median(p_y[side_mask]))
    trigger_mckd = bool(
        abs(residual_m["excess_kurtosis"]) > 1.0
        or residual_m["crest_factor"] > 6.0
        or np.max(np.abs(acf[1:101])) > 0.08
    )
    rows = []
    for source, values in [("raw", raw_m), ("residual", residual_m)]:
        for metric, value in values.items():
            rows.append({"source": source, "metric": metric, "value": value})
    rows.extend([
        {"source": "residual", "metric": "acf_lag_1", "value": float(acf[1])},
        {"source": "residual", "metric": "acf_lag_10", "value": float(acf[10])},
        {"source": "residual", "metric": "acf_lag_50", "value": float(acf[50])},
        {"source": "residual", "metric": "max_abs_acf_lag_1_100", "value": float(np.max(np.abs(acf[1:101])))},
        {"source": "spectrum", "metric": "target_peak_suppression_db", "value": target_suppression_db},
        {"source": "spectrum", "metric": "largest_side_peak_to_local_median", "value": side_ratio},
        {"source": "decision", "metric": "trigger_mckd_branch", "value": float(trigger_mckd)},
    ])
    bands = []
    for source, signal_values in [("preprocessed", y), ("residual", residual)]:
        for row in band_power_rows(signal_values, fs):
            bands.append({"source": source, **row})
    return rows, bands


def parameter_covariance(t: np.ndarray, fit: dict) -> tuple[np.ndarray, np.ndarray]:
    """参数协方差：解析 Jacobian 推导 σ²(JᵀJ)⁻¹，给出参数的标准误和相关系数。"""
    # [AI-1] 辅助解析 Jacobian 构建与伪逆协方差估计
    center = fit["center_time_s"]
    tc = t - center
    f = fit["frequency_hz"]
    a, b = fit["a_centered"], fit["b_centered"]
    angle = 2.0 * np.pi * f * tc
    derivative_f = 2.0 * np.pi * tc * (a * np.cos(angle) - b * np.sin(angle))
    jacobian = np.column_stack([np.sin(angle), np.cos(angle), np.ones_like(tc), derivative_f])
    dof = max(len(t) - 4, 1)
    sigma2 = fit["sse"] / dof
    covariance = sigma2 * np.linalg.pinv(jacobian.T @ jacobian)  # [AI-1] 辅助伪逆求解避免设计矩阵病态
    theta = np.asarray([a, b, fit["offset"], f], dtype=float)
    return theta, covariance


def bootstrap_parameters(t: np.ndarray, fit: dict, runs: int, seed: int) -> tuple[list[dict], dict]:
    """局部渐近正态抽样：多元正态 10000 次抽取参数区间，非残差 Bootstrap。"""
    # [AI-1] 辅助实现协方差抽样与 bootstrap 术语修正（实为渐近正态近似）
    theta, covariance = parameter_covariance(t, fit)
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(theta, covariance, size=runs, check_valid="ignore")
    a, b, offset, frequency = draws.T
    amplitude = np.hypot(a, b)
    phase_center = np.arctan2(b, a)
    phase_origin = wrap_phase(phase_center - 2.0 * np.pi * frequency * fit["center_time_s"])
    point_phase = fit["phase_origin_rad"]
    phase_origin_continuous = align_phase_to_reference(phase_origin, point_phase)
    quantities = {
        "frequency_hz": (frequency, fit["frequency_hz"]),
        "amplitude": (amplitude, fit["amplitude"]),
        "phase_origin_rad": (phase_origin_continuous, point_phase),
        "offset": (offset, fit["offset"]),
    }
    rows = []
    for name, (values, point) in quantities.items():
        low, high = np.quantile(values, [0.025, 0.975])
        rows.append({
            "parameter": name,
            "estimate": float(point),
            "ci95_low": float(low),
            "ci95_high": float(high),
            "bootstrap_std": float(np.std(values, ddof=1)),
            "runs": runs,
            "method": "linearized parametric bootstrap",
            "random_seed": seed,
        })
    return rows, {"draws": draws, "amplitude": amplitude, "phase_origin": phase_origin}


def joint_segment_fit(t: np.ndarray, y: np.ndarray, initial_f: float, fs: float, segment_seconds: float = 50.0):
    """分段频率恒定性检验：比较各段独立频率 vs 公共频率模型的 BIC，验证频率是否恒定。"""
    # [AI-1] 辅助分段 BIC 比较框架与短段丢弃逻辑
    segment_len = int(round(segment_seconds * fs))
    segments = []
    dropped_samples = 0
    for start in range(0, len(y), segment_len):
        end = min(start + segment_len, len(y))
        if end - start >= int(10 * fs):
            segments.append((t[start:end], y[start:end]))
        else:
            dropped_samples += end - start
    if dropped_samples >= int(fs):
        warnings.warn(  # [AI-1] 辅助添加短段丢弃 warning 提示
            f"Skipped {dropped_samples} sample(s) in short trailing segment(s) in joint_segment_fit.",
            RuntimeWarning,
            stacklevel=2,
        )
    if not segments:
        raise ValueError("No segments are at least 10 seconds long; cannot run joint segment fit.")

    def total_sse(frequency: float) -> float:
        return float(sum(harmonic_fit(st, sy, frequency)["sse"] for st, sy in segments))

    common_f = golden_minimize(total_sse, initial_f - 0.01, initial_f + 0.01)
    rows = []
    common_sse = 0.0
    independent_sse = 0.0
    for idx, (st, sy) in enumerate(segments, 1):
        common = harmonic_fit(st, sy, common_f)
        independent = refine_frequency(st, sy, initial_f, half_width=max(3.0 * fs / len(st), 0.01))  # [AI-1] 辅助自适 half_width
        common_sse += common["sse"]
        independent_sse += independent["sse"]
        signal_power = float(np.mean(common["fit"] ** 2))
        noise_power = float(np.mean(common["residual"] ** 2))
        rows.append({
            "segment_id": idx,
            "start_s": float(st[0]),
            "end_s": float(st[-1]),
            "sample_count": len(st),
            "common_frequency_hz": common_f,
            "independent_frequency_hz": independent["frequency_hz"],
            "independent_deviation_from_common_hz": independent["frequency_hz"] - common_f,
            "amplitude": common["amplitude"],
            "phase_origin_rad": common["phase_origin_rad"],
            "estimated_snr_db": 10.0 * math.log10(signal_power / max(noise_power, 1e-300)),
            "residual_rmse": common["rmse"],
        })
    n = sum(len(sy) for _, sy in segments)
    k_common = 1 + 3 * len(segments)
    k_independent = 4 * len(segments)
    bic_common = n * math.log(max(common_sse / n, 1e-300)) + k_common * math.log(n)
    bic_independent = n * math.log(max(independent_sse / n, 1e-300)) + k_independent * math.log(n)
    comparison = [
        {"model": "common frequency", "parameters": k_common, "sse": common_sse, "bic": bic_common},
        {"model": "independent frequencies", "parameters": k_independent, "sse": independent_sse, "bic": bic_independent},
    ]
    return rows, comparison


def segment_length_sensitivity(
    t: np.ndarray,
    y: np.ndarray,
    initial_f: float,
    fs: float,
    segment_lengths: tuple[float, ...] = (25.0, 50.0, 100.0),
) -> tuple[list[dict], list[dict]]:
    """Compare common-frequency conclusions across several window lengths."""
    detail_rows: list[dict] = []
    summary_rows: list[dict] = []
    for seconds in segment_lengths:
        rows, comparison = joint_segment_fit(t, y, initial_f, fs, segment_seconds=seconds)
        for row in rows:
            detail_rows.append({"segment_seconds": seconds, **row})
        models = {row["model"]: row for row in comparison}
        deviations = np.abs(np.asarray([row["independent_deviation_from_common_hz"] for row in rows], dtype=float))
        amplitudes = np.asarray([row["amplitude"] for row in rows], dtype=float)
        snr = np.asarray([row["estimated_snr_db"] for row in rows], dtype=float)
        common_bic = float(models["common frequency"]["bic"])
        independent_bic = float(models["independent frequencies"]["bic"])
        summary_rows.append({
            "segment_seconds": seconds,
            "segment_count": len(rows),
            "common_frequency_hz": rows[0]["common_frequency_hz"],
            "mean_abs_frequency_deviation_hz": float(np.mean(deviations)),
            "std_abs_frequency_deviation_hz": float(np.std(deviations, ddof=1)) if len(deviations) > 1 else 0.0,
            "max_abs_frequency_deviation_hz": float(np.max(deviations)),
            "amplitude_coefficient_of_variation": float(np.std(amplitudes, ddof=1) / np.mean(amplitudes)),
            "snr_min_db": float(np.min(snr)),
            "snr_max_db": float(np.max(snr)),
            "common_frequency_bic": common_bic,
            "independent_frequencies_bic": independent_bic,
            "common_frequency_sse": float(models["common frequency"]["sse"]),
            "independent_frequencies_sse": float(models["independent frequencies"]["sse"]),
            "bic_advantage_common": independent_bic - common_bic,
            "common_frequency_preferred": independent_bic > common_bic,
        })
    return detail_rows, summary_rows


def fft_zero_phase_bandpass(x: np.ndarray, fs: float, center: float = 2.0) -> np.ndarray:
    n = len(x)
    freq = np.fft.rfftfreq(n, 1.0 / fs)
    inner_lo, inner_hi = center - 0.25, center + 0.25
    outer_lo, outer_hi = center - 0.50, center + 0.50
    weight = np.zeros_like(freq)
    weight[(freq >= inner_lo) & (freq <= inner_hi)] = 1.0
    left = (freq >= outer_lo) & (freq < inner_lo)
    right = (freq > inner_hi) & (freq <= outer_hi)
    weight[left] = 0.5 * (1.0 - np.cos(np.pi * (freq[left] - outer_lo) / (inner_lo - outer_lo)))
    weight[right] = 0.5 * (1.0 + np.cos(np.pi * (freq[right] - inner_hi) / (outer_hi - inner_hi)))
    return np.fft.irfft(np.fft.rfft(x) * weight, n=n)


def analytic_signal(x: np.ndarray) -> np.ndarray:
    n = len(x)
    X = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = h[n // 2] = 1.0
        h[1:n // 2] = 2.0
    else:
        h[0] = 1.0
        h[1:(n + 1) // 2] = 2.0
    return np.fft.ifft(X * h)


def targeted_filter_comparison(t: np.ndarray, y: np.ndarray, fit: dict, fs: float) -> tuple[list[dict], np.ndarray, np.ndarray]:
    filtered = fft_zero_phase_bandpass(y, fs, fit["frequency_hz"])
    analytic = analytic_signal(filtered)
    envelope = np.abs(analytic)
    reference = fit["fit"] - fit["offset"]
    edge_n = int(round(5.0 * fs))
    central = np.zeros(len(y), dtype=bool)
    central[edge_n:-edge_n] = True
    corr = float(np.corrcoef(reference[central], filtered[central])[0, 1])
    rmse_center = float(np.sqrt(np.mean((reference[central] - filtered[central]) ** 2)))
    edge = ~central
    rmse_edge = float(np.sqrt(np.mean((reference[edge] - filtered[edge]) ** 2)))
    amp_filter = float(np.median(envelope[central]))
    rows = [
        {"metric": "central_waveform_correlation", "harmonic_regression": 1.0, "targeted_filter": corr},
        {"metric": "central_rmse_to_harmonic_reference", "harmonic_regression": 0.0, "targeted_filter": rmse_center},
        {"metric": "edge_rmse_to_harmonic_reference", "harmonic_regression": 0.0, "targeted_filter": rmse_edge},
        {"metric": "estimated_amplitude", "harmonic_regression": fit["amplitude"], "targeted_filter": amp_filter},
        {"metric": "amplitude_difference", "harmonic_regression": 0.0, "targeted_filter": amp_filter - fit["amplitude"]},
    ]
    return rows, filtered, envelope


def fft_zero_phase_lowpass(x: np.ndarray, fs: float, pass_hz: float = 8.0, stop_hz: float = 10.0) -> np.ndarray:
    """FFT low-pass used only as anti-aliasing before SSA downsampling."""
    n = len(x)
    freq = np.fft.rfftfreq(n, 1.0 / fs)
    weight = np.ones_like(freq)
    weight[freq >= stop_hz] = 0.0
    taper = (freq > pass_hz) & (freq < stop_hz)
    weight[taper] = 0.5 * (1.0 + np.cos(np.pi * (freq[taper] - pass_hz) / (stop_hz - pass_hz)))
    return np.fft.irfft(np.fft.rfft(x) * weight, n=n)


def _ssa_reconstruct_pair(x: np.ndarray, fs: float, window: int, target_hz: float) -> tuple[np.ndarray, tuple[int, int], float]:
    """Reconstruct the two SSA components most concentrated around target_hz."""
    centered = np.asarray(x, dtype=float) - float(np.mean(x))
    if window > len(centered):
        raise ValueError(f"SSA window ({window}) cannot exceed signal length ({len(centered)}).")
    trajectory = np.lib.stride_tricks.sliding_window_view(centered, window).T
    columns = trajectory.shape[1]
    covariance = trajectory @ trajectory.T / columns
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    candidate_count = min(12, len(order))
    candidates = order[:candidate_count]
    weights = np.convolve(np.ones(window), np.ones(columns))
    components: dict[int, np.ndarray] = {}
    scores = []
    for rank, index in enumerate(candidates, 1):
        u = eigenvectors[:, index]
        principal = u @ trajectory
        component = np.convolve(u, principal) / weights
        components[int(index)] = component
        freq, power = spectrum(component, fs)
        target = (freq >= target_hz - 0.20) & (freq <= target_hz + 0.20)
        useful = (freq >= 0.25) & (freq <= min(8.0, 0.49 * fs))
        concentration = float(np.sum(power[target]) / max(np.sum(power[useful]), 1e-30))
        scores.append((concentration, int(index), rank))
    selected_entries = sorted(scores, reverse=True)[:2]
    selected_indices = tuple(index for _, index, _ in selected_entries)
    selected_ranks = tuple(rank for _, _, rank in selected_entries)
    reconstructed = components[selected_indices[0]] + components[selected_indices[1]]
    selected_variance = float((eigenvalues[selected_indices[0]] + eigenvalues[selected_indices[1]]) / np.sum(eigenvalues))
    return reconstructed, selected_ranks, selected_variance


def ssa_recovery_comparison(
    t: np.ndarray,
    y: np.ndarray,
    fit: dict,
    fs: float,
    window_points: tuple[int, ...] = (500, 1000, 2000),
    downsample_factor: int = 5,
) -> tuple[list[dict], np.ndarray, int]:
    """Run economical SSA at 20 Hz and compare it with harmonic regression.

    The listed window sizes use original 100 Hz sample units.  An 8 Hz
    anti-aliasing low-pass is applied before decimation; no 2 Hz band-pass is
    used, so SSA remains a data-driven decomposition comparison.
    """
    lowpassed = fft_zero_phase_lowpass(y, fs)
    t_ds = t[::downsample_factor]
    y_ds = lowpassed[::downsample_factor]
    fs_ds = fs / downsample_factor
    reference = fit["fit"] - fit["offset"]
    edge_n = int(round(5.0 * fs))
    central = np.zeros(len(y), dtype=bool)
    central[edge_n:-edge_n] = True
    rows: list[dict] = []
    recovered_by_window: dict[int, np.ndarray] = {}
    for original_window in window_points:
        window_ds = max(20, int(round(original_window / downsample_factor)))
        if window_ds > len(y_ds):
            warnings.warn(
                f"Skipped SSA window {original_window} original points because {window_ds} downsampled points exceed signal length {len(y_ds)}.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        recovered_ds, selected, variance_share = _ssa_reconstruct_pair(
            y_ds, fs_ds, window_ds, fit["frequency_hz"]
        )
        recovered = np.interp(t, t_ds, recovered_ds)
        recovered_by_window[original_window] = recovered
        estimate = refine_frequency(t, recovered, fit["frequency_hz"], half_width=0.01)
        corr = float(np.corrcoef(reference[central], recovered[central])[0, 1])
        rmse = float(np.sqrt(np.mean((reference[central] - recovered[central]) ** 2)))
        residual_std = float(np.std(y - recovered))
        freq, power = spectrum(recovered, fs)
        target = (freq >= fit["frequency_hz"] - 0.20) & (freq <= fit["frequency_hz"] + 0.20)
        useful = (freq >= 0.25) & (freq <= 8.0)
        rows.append({
            "window_points_original": original_window,
            "window_seconds": round(original_window / fs, 6),
            "downsample_factor": downsample_factor,
            "ssa_sampling_rate_hz": fs_ds,
            "selected_component_1": selected[0],
            "selected_component_2": selected[1],
            "selected_eigenvalue_fraction": variance_share,
            "estimated_frequency_hz": estimate["frequency_hz"],
            "estimated_amplitude": estimate["amplitude"],
            "correlation_to_harmonic": corr,
            "rmse_to_harmonic": rmse,
            "residual_std": residual_std,
            "target_band_power_fraction": float(np.sum(power[target]) / max(np.sum(power[useful]), 1e-30)),
        })
    if not rows:
        raise ValueError("No valid SSA windows remain after downsampling; cannot run SSA comparison.")
    best_window = max(rows, key=lambda row: row["correlation_to_harmonic"])["window_points_original"]
    return rows, recovered_by_window[int(best_window)], int(best_window)


def fast_frequency_estimate(t: np.ndarray, x: np.ndarray, fs: float, expected: float = 2.0) -> dict:
    y, _ = linear_detrend(t, x)
    n = len(y)
    freq = np.fft.rfftfreq(n, 1.0 / fs)
    power = np.abs(np.fft.rfft(y * np.hanning(n))) ** 2
    mask = (freq >= expected - 0.5) & (freq <= expected + 0.5)
    indexes = np.where(mask)[0]
    k = int(indexes[np.argmax(power[mask])])
    if 0 < k < len(power) - 1:
        p = np.log(power[k - 1:k + 2] + 1e-300)
        denom = p[0] - 2.0 * p[1] + p[2]
        delta = 0.5 * (p[0] - p[2]) / denom if abs(denom) > 1e-15 else 0.0
    else:
        delta = 0.0
    frequency = float((k + delta) * fs / n)
    # Three variable-projection Gauss-Newton updates.  The frequency derivative
    # is projected away from the linear sine/cosine/offset space, avoiding the
    # dozens of full-length least-squares evaluations used by a generic 1-D
    # optimizer.
    lower, upper = expected - 0.5, expected + 0.5
    for _ in range(3):
        current = harmonic_fit(t, y, frequency)
        tc = t - current["center_time_s"]
        angle = 2.0 * np.pi * frequency * tc
        X = np.column_stack([np.sin(angle), np.cos(angle), np.ones_like(tc)])
        derivative = 2.0 * np.pi * tc * (
            current["a_centered"] * np.cos(angle) - current["b_centered"] * np.sin(angle)
        )
        derivative_perp = derivative - X @ np.linalg.lstsq(X, derivative, rcond=None)[0]
        denom = float(np.dot(derivative_perp, derivative_perp))
        if denom <= 1e-30:
            break
        step = float(np.dot(derivative_perp, current["residual"]) / denom)
        frequency = float(np.clip(frequency + step, lower, upper))
    return harmonic_fit(t, y, frequency)


def simulation_validation(
    fs: float,
    n: int,
    amplitude: float,
    seed: int,
    runs_per_snr: int = 200,
    f_true: float = 2.0,
) -> list[dict]:
    """合成数据 Monte Carlo 验证：评估频率/振幅/相位的偏差、RMSE 和 95% 区间覆盖率。"""
    # [AI-1] 辅助 5 级 SNR 扫描与 200 次 MC 试验编排
    rng = np.random.default_rng(seed + 100)
    t = np.arange(n, dtype=float) / fs
    rows = []
    for snr_db in [-20.0, -15.0, -12.0, -10.0, -5.0]:
        freq_errors, amp_rel_errors, phase_errors, waveform_rmse = [], [], [], []
        cover_f, cover_a, cover_phi = [], [], []
        for _ in range(runs_per_snr):
            phi_true = rng.uniform(-np.pi, np.pi)
            truth = amplitude * np.sin(2.0 * np.pi * f_true * t + phi_true)
            signal_power = amplitude**2 / 2.0
            noise_std = math.sqrt(signal_power / (10.0 ** (snr_db / 10.0)))  # [AI-1] 辅助 SNR 逆推噪声标准差
            x = truth + rng.normal(0.0, noise_std, n)
            est = fast_frequency_estimate(t, x, fs, f_true)
            recovered = est["amplitude"] * np.sin(2.0 * np.pi * est["frequency_hz"] * t + est["phase_origin_rad"])
            freq_errors.append(abs(est["frequency_hz"] - f_true))
            amp_rel_errors.append(abs(est["amplitude"] - amplitude) / amplitude)
            aligned_phase = float(align_phase_to_reference(est["phase_origin_rad"], phi_true))
            phase_errors.append(abs(aligned_phase - phi_true))
            waveform_rmse.append(float(np.sqrt(np.mean((recovered - truth) ** 2))))

            theta, cov = parameter_covariance(t, est)
            se_f = math.sqrt(max(cov[3, 3], 0.0))  # [AI-1] 辅助协方差矩阵提取频率标准误
            a, b = est["a_centered"], est["b_centered"]
            A = max(est["amplitude"], 1e-15)
            grad_A = np.asarray([a / A, b / A, 0.0, 0.0])
            se_A = math.sqrt(max(float(grad_A @ cov @ grad_A), 0.0))
            grad_pc = np.asarray([-b / A**2, a / A**2, 0.0, 0.0])
            grad_po = grad_pc.copy()
            grad_po[3] = -2.0 * np.pi * est["center_time_s"]
            se_phi = math.sqrt(max(float(grad_po @ cov @ grad_po), 0.0))
            cover_f.append(abs(est["frequency_hz"] - f_true) <= 1.96 * se_f)
            cover_a.append(abs(est["amplitude"] - amplitude) <= 1.96 * se_A)
            cover_phi.append(phase_in_circular_ci(phi_true, est["phase_origin_rad"], 1.96 * se_phi))
        rows.append({
            "snr_db": snr_db,
            "runs": runs_per_snr,
            "sample_count": n,
            "mean_abs_frequency_error_hz": float(np.mean(freq_errors)),
            "mean_amplitude_relative_error": float(np.mean(amp_rel_errors)),
            "mean_abs_phase_error_rad": float(np.mean(phase_errors)),
            "mean_waveform_rmse": float(np.mean(waveform_rmse)),
            "frequency_ci95_coverage": float(np.mean(cover_f)),
            "amplitude_ci95_coverage": float(np.mean(cover_a)),
            "phase_ci95_coverage": float(np.mean(cover_phi)),
        })
    return rows
