"""Computation routines for the Q1 GLRT model."""

from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from q1_model_compare import (
    Config,
    estimate_glrt_threshold,
    estimate_sinusoid,
    fft_spectrum,
    frequency_bounds,
    glrt_stat_from_fft,
    load_single_source,
    preprocess,
    refine_frequency,
    synthetic_signal,
)


# [AI-1] 辅助 GLRT 参数字典集中管理，供输出报告引用
GLRT_PARAMETERS = {
    "signal_model": "x(t)=A sin(2*pi*f*t+phi)+n(t)",
    "preprocess": "linear detrend",
    "frequency_search_min_hz": 0.05,
    "frequency_search_max_hz": 49.5,
    "target_false_alarm_rate": 0.05,
    "threshold_method": "pure-noise Monte Carlo on max GLRT statistic",
    "frequency_refinement": "bounded 1D least-squares around coarse FFT-bin peak",
}


@lru_cache(maxsize=4)
def _load_q1_data_cached(data_path: str) -> tuple[np.ndarray, np.ndarray, float]:
    """LRU 缓存数据加载：避免重复读取 Excel 文件。"""
    # [AI-1] 辅助 LRU 缓存装饰器配置（maxsize=4）
    return load_single_source(Path(data_path))


def load_q1_data(cfg: Config) -> tuple[np.ndarray, np.ndarray, float]:
    """数据加载缓存代理：路径规范化后转发 LRU 缓存。"""
    # [AI-1] 辅助路径规范化与缓存转发
    return _load_q1_data_cached(str(Path(cfg.data_path).resolve()))


def require_frequency_mask(freqs: np.ndarray, cfg: Config) -> np.ndarray:
    """频率掩码校验：确保搜索区间内至少有一个 FFT bin。"""
    # [AI-1] 辅助空掩码保护与错误提示信息
    mask = frequency_bounds(freqs, cfg)
    if not np.any(mask):
        raise ValueError(
            f"No frequency bins in search range [{cfg.f_min:g}, {cfg.f_max:g}] Hz. "
            "Check --f-min/--f-max against the sampling rate."
        )
    return mask


def run_glrt_q1(cfg: Config) -> dict[str, float | bool | str]:
    """Q1 GLRT 主流程：加载→去趋势→周期图扫描→MC 门限→频率精修→信号恢复。"""
    # [AI-1] 辅助编排完整 GLRT 检测管线
    t, x, fs = load_q1_data(cfg)
    y = preprocess(x)  # [AI-1] 辅助确认去趋势预处理步骤
    freqs, stat = glrt_stat_from_fft(x, fs, cfg)
    mask = require_frequency_mask(freqs, cfg)
    search_freqs = freqs[mask]
    search_stat = stat[mask]
    best_local = int(np.argmax(search_stat))  # [AI-1] 辅助频率掩码 argmax 粗定位
    coarse_freq = float(search_freqs[best_local])
    score = float(search_stat[best_local])
    threshold = estimate_glrt_threshold(len(y), fs, cfg)  # [AI-1] 辅助纯噪声 MC 门限校准
    refined = refine_frequency(t, y, coarse_freq, fs)  # [AI-1] 辅助 Brent 有界连续频率精修
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
    """GLRT 检测：去趋势→归一化周期图→粗检峰→MC 门限判决→精修频率。"""
    # [AI-1] 辅助 GLRT 检测端到端封装与结果字典标准化
    y = preprocess(x)
    freqs, stat = glrt_stat_from_fft(x, fs, cfg)
    mask = require_frequency_mask(freqs, cfg)
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
    """FFT 峰值法（与 GLRT 数学等价）：同一周期图、同一 MC 门限，二者检测结论一致。"""
    # [AI-1] 辅助 FFT 等价实现封装，共享 GLRT 统计量与门限
    y = preprocess(x)
    freqs, stat = glrt_stat_from_fft(x, fs, cfg)
    mask = require_frequency_mask(freqs, cfg)
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


def recovered_signal(t: np.ndarray, x: np.ndarray, freq: float) -> np.ndarray:
    """最小二乘重建正弦：在指定频率下拟合 sin/cos/offset，返回拟合波形。"""
    # [AI-1] 辅助最小二乘重建与波形返回
    y = preprocess(x)
    omega_t = 2.0 * np.pi * freq * t
    design = np.column_stack([np.sin(omega_t), np.cos(omega_t), np.ones_like(t)])
    coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
    return design @ coeffs


def analyze_preprocessing_and_noise(cfg: Config, result: dict[str, float | bool | str]) -> pd.DataFrame:
    """噪声诊断：计算 SNR、残差统计矩（偏度/峰度/自相关），验证白噪声假设。"""
    # [AI-1] 辅助残差统计矩与 SNR 估计诊断管线
    t, x, fs = load_q1_data(cfg)
    y = preprocess(x)
    s_hat = recovered_signal(t, x, float(result["refined_frequency_hz"]))
    residual = y - s_hat
    signal_power = float(np.mean(s_hat * s_hat))
    residual_power = float(np.mean(residual * residual))
    if signal_power <= 0.0 or residual_power <= 0.0:
        estimated_snr_db = float("nan")
    else:
        estimated_snr_db = 10.0 * math.log10(signal_power / residual_power)

    rows = [
        {"metric": "sample_count", "value": len(x), "note": "样本数量"},
        {"metric": "sampling_rate_hz", "value": fs, "note": "由时间列估计"},
        {"metric": "duration_s", "value": t[-1] - t[0], "note": "观测时长"},
        {"metric": "raw_mean", "value": float(np.mean(x)), "note": "预处理前均值"},
        {"metric": "raw_std", "value": float(np.std(x)), "note": "预处理前标准差"},
        {"metric": "preprocessed_mean", "value": float(np.mean(y)), "note": "线性去趋势后均值"},
        {"metric": "preprocessed_std", "value": float(np.std(y)), "note": "线性去趋势后标准差"},
        {"metric": "residual_mean", "value": float(np.mean(residual)), "note": "移除拟合正弦后的均值"},
        {"metric": "residual_std", "value": float(np.std(residual)), "note": "噪声标准差估计"},
        {"metric": "residual_skewness", "value": float(stats.skew(residual)), "note": "接近 0 表示近似对称"},
        {"metric": "residual_excess_kurtosis", "value": float(stats.kurtosis(residual)), "note": "接近 0 表示近似 Gaussian"},
        {"metric": "fitted_signal_rms", "value": float(np.sqrt(signal_power)), "note": "提取正弦信号 RMS"},
        {"metric": "estimated_noise_rms", "value": float(np.sqrt(residual_power)), "note": "残差噪声 RMS"},
        {"metric": "estimated_snr_db", "value": estimated_snr_db, "note": "10log10(信号功率/噪声功率)"},
    ]
    return pd.DataFrame(rows)


def build_parameter_table(cfg: Config) -> pd.DataFrame:
    """参数汇总表：将 GLRT 所有配置以 DataFrame 形式输出供论文引用。"""
    # [AI-1] 辅助参数表标准化生成
    rows = [
        {"parameter": "f_min", "value": cfg.f_min, "unit": "Hz", "meaning": "频率搜索下限"},
        {"parameter": "f_max", "value": cfg.f_max, "unit": "Hz", "meaning": "频率搜索上限"},
        {"parameter": "p_fa", "value": cfg.p_fa, "unit": "-", "meaning": "目标误报率"},
        {"parameter": "glrt_mc", "value": cfg.glrt_mc, "unit": "runs", "meaning": "阈值 Monte Carlo 次数"},
        {"parameter": "random_seed", "value": cfg.random_seed, "unit": "-", "meaning": "随机种子"},
        {"parameter": "preprocess", "value": "linear detrend", "unit": "-", "meaning": "去直流和线性趋势"},
        {"parameter": "refine_half_width", "value": "max(3*fs/N, 0.01)", "unit": "Hz", "meaning": "局部频率精修窗口"},
        {"parameter": "success_tolerance", "value": 0.05, "unit": "Hz", "meaning": "仿真成功判据的频率误差容限"},
    ]
    return pd.DataFrame(rows)


def run_segment_validation(cfg: Config, segment_seconds: float = 50.0) -> pd.DataFrame:
    """分段稳定性验证：将数据切为 50s 段，各段独立 GLRT 检测，检查频率恒定性。"""
    # [AI-1] 辅助分段 GLRT 编排与频率偏差统计
    t, x, fs = load_q1_data(cfg)
    segment_len = int(round(segment_seconds * fs))
    rows = []
    for start in range(0, len(x), segment_len):
        end = min(start + segment_len, len(x))
        if end - start < int(10 * fs):
            continue
        seg_t = t[start:end]
        seg_x = x[start:end]
        detected = glrt_detect_signal(seg_t, seg_x, fs, cfg)
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
    return pd.DataFrame(rows)


def run_fft_glrt_simulation(
    cfg: Config,
    f0: float,
    amplitude: float,
    fs: float,
    n: int,
    sim_mc: int,
) -> pd.DataFrame:
    """Monte Carlo 对比仿真：在 −25 至 −5 dB 范围比较 FFT 与 GLRT 的检测概率。"""
    # [AI-1] 辅助 SNR 扫描网格与随机种子偏移设计
    rng = np.random.default_rng(cfg.random_seed + 99)
    snr_values = [-25.0, -22.0, -20.0, -18.0, -15.0, -12.0, -10.0, -5.0]
    sim_n = n  # [AI-1] 辅助统一仿真样本数 N=40001
    sim_cfg = Config(**{**cfg.__dict__, "glrt_mc": max(120, min(cfg.glrt_mc, 300))})  # [AI-1] 辅助仿真内 MC 门限自适应缩减
    rows = []
    tolerance = 0.05

    for snr_db in snr_values:
        per_method = {"FFT peak": {"success": [], "error": []}, "GLRT": {"success": [], "error": []}}
        half_bin = fs / (2.0 * sim_n)
        for _ in range(sim_mc):
            f0_trial = f0 + rng.uniform(-half_bin, half_bin)  # [AI-1] 辅助随机非栅格频率偏移，避免栅格偏好
            sim_t, sim_x = synthetic_signal(fs, sim_n, f0_trial, amplitude, snr_db, rng)
            fft_res = fft_peak_detect_signal(sim_t, sim_x, fs, sim_cfg)
            fft_error = abs(float(fft_res["refined_frequency_hz"]) - f0_trial)
            per_method["FFT peak"]["success"].append(bool(fft_res["detected"]) and fft_error <= tolerance)
            per_method["FFT peak"]["error"].append(fft_error)

            glrt_res = glrt_detect_signal(sim_t, sim_x, fs, sim_cfg)
            glrt_error = abs(float(glrt_res["refined_frequency_hz"]) - f0_trial)
            per_method["GLRT"]["success"].append(bool(glrt_res["detected"]) and glrt_error <= tolerance)
            per_method["GLRT"]["error"].append(glrt_error)

        for method, values in per_method.items():
            errors = np.asarray(values["error"], dtype=float)
            rows.append(
                {
                    "method": method,
                    "snr_db": snr_db,
                    "p_detect": float(np.mean(values["success"])),  # [AI-1] 辅助检测概率与频率误差统计汇总
                    "mean_abs_frequency_error_hz": float(np.mean(errors)),
                    "std_abs_frequency_error_hz": float(np.std(errors)),
                    "mc_runs": sim_mc,
                    "sample_count": sim_n,
                    "success_tolerance_hz": tolerance,
                }
            )
    return pd.DataFrame(rows)
