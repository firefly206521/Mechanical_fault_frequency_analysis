"""
Q1 model comparison for weak sinusoidal fault-frequency detection.

The script reads data.xlsx / sheet "单源故障", runs several frequency
detection models under one interface, refines each coarse estimate with
least-squares fitting, and writes comparison tables and plots.
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import optimize, signal
from sklearn.utils.extmath import randomized_svd


FS_EXPECTED = 100.0
SHEET_SINGLE = "单源故障"


@dataclass
class Config:
    data_path: Path
    output_dir: Path
    f_min: float = 0.05
    f_max: float = 49.5
    p_fa: float = 0.05
    cfar_guard: int = 4
    cfar_train: int = 80
    cfar_scale: float = 25.0
    glrt_mc: int = 200
    sim_mc: int = 8
    random_seed: int = 20260619
    run_simulation: bool = True


def load_single_source(data_path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    df = pd.read_excel(data_path, sheet_name=SHEET_SINGLE)
    if list(df.columns[:2]) != ["t", "x(t)"]:
        raise ValueError(f"Unexpected columns in {data_path}: {list(df.columns)}")

    t = pd.to_numeric(df["t"], errors="coerce").to_numpy(dtype=float)
    x = pd.to_numeric(df["x(t)"], errors="coerce").to_numpy(dtype=float)
    if np.isnan(t).any() or np.isnan(x).any():
        raise ValueError("Input sheet contains non-numeric t or x(t) values.")

    dt = np.diff(t)
    valid_time = (
        len(t) > 2
        and np.all(dt > 0)
        and abs(float(np.median(dt)) - 1.0 / FS_EXPECTED) < 1e-6
    )
    if valid_time:
        fs = 1.0 / float(np.median(dt))
    else:
        fs = FS_EXPECTED
        t = np.arange(len(x), dtype=float) / fs

    return t, x, fs


def preprocess(x: np.ndarray) -> np.ndarray:
    return signal.detrend(np.asarray(x, dtype=float), type="linear")


def frequency_bounds(freqs: np.ndarray, cfg: Config) -> np.ndarray:
    return (freqs >= cfg.f_min) & (freqs <= cfg.f_max)


def require_frequency_mask(freqs: np.ndarray, cfg: Config) -> np.ndarray:
    mask = frequency_bounds(freqs, cfg)
    if not np.any(mask):
        raise ValueError(
            f"No frequency bins in search range [{cfg.f_min:g}, {cfg.f_max:g}] Hz. "
            "Check f_min/f_max against the sampling rate."
        )
    return mask


def estimate_sinusoid(t: np.ndarray, x: np.ndarray, freq: float) -> dict[str, float]:
    omega_t = 2.0 * np.pi * freq * t
    design = np.column_stack([np.sin(omega_t), np.cos(omega_t), np.ones_like(t)])
    coeffs, *_ = np.linalg.lstsq(design, x, rcond=None)
    fit = design @ coeffs
    residual = x - fit
    a, b, c = coeffs
    amplitude = float(np.hypot(a, b))
    phase = float(math.atan2(b, a))
    rmse = float(np.sqrt(np.mean(residual * residual)))
    explained = 1.0 - float(np.var(residual) / np.var(x))
    return {
        "frequency": float(freq),
        "amplitude": amplitude,
        "phase": phase,
        "offset": float(c),
        "rmse": rmse,
        "explained_var": explained,
    }


def refine_frequency(
    t: np.ndarray,
    x: np.ndarray,
    coarse_freq: float,
    fs: float,
    half_width: float | None = None,
) -> dict[str, float]:
    if not np.isfinite(coarse_freq) or coarse_freq <= 0:
        return estimate_sinusoid(t, x, max(0.001, coarse_freq))

    if half_width is None:
        half_width = max(fs / len(x) * 3.0, 0.01)
    lo = max(0.001, coarse_freq - half_width)
    hi = min(fs / 2.0 - 1e-6, coarse_freq + half_width)

    def objective(freq: float) -> float:
        return estimate_sinusoid(t, x, float(freq))["rmse"]

    result = optimize.minimize_scalar(objective, bounds=(lo, hi), method="bounded")
    refined = float(result.x) if result.success else float(coarse_freq)
    return estimate_sinusoid(t, x, refined)


def timed_model(name: str, func, t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    start = time.perf_counter()
    out = func(t, x, fs, cfg)
    runtime_ms = (time.perf_counter() - start) * 1000.0
    out["model_name"] = name
    out["runtime_ms"] = runtime_ms
    refined = refine_frequency(t, preprocess(x), out["f0_hat"], fs)
    out["f0_refined"] = refined["frequency"]
    out["amplitude"] = refined["amplitude"]
    out["phase"] = refined["phase"]
    out["fit_rmse"] = refined["rmse"]
    out["fit_explained_var"] = refined["explained_var"]
    return out


def fft_spectrum(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    y = preprocess(x)
    window = np.hanning(len(y))
    spec = np.fft.rfft(y * window)
    freqs = np.fft.rfftfreq(len(y), d=1.0 / fs)
    power = np.abs(spec) ** 2
    return freqs, power


def model_fft_peak(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    freqs, power = fft_spectrum(x, fs)
    mask = require_frequency_mask(freqs, cfg)
    idx = np.where(mask)[0][np.argmax(power[mask])]
    return {
        "detected": True,
        "f0_hat": float(freqs[idx]),
        "score": float(power[idx]),
        "threshold": np.nan,
        "notes": "maximum Hann-windowed FFT peak",
    }


def model_welch_psd(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    y = preprocess(x)
    freqs, psd = signal.welch(
        y,
        fs=fs,
        window="hann",
        nperseg=8192,
        noverlap=4096,
        scaling="spectrum",
    )
    mask = require_frequency_mask(freqs, cfg)
    idx = np.where(mask)[0][np.argmax(psd[mask])]
    return {
        "detected": True,
        "f0_hat": float(freqs[idx]),
        "score": float(psd[idx]),
        "threshold": np.nan,
        "notes": "Welch averaged spectrum, lower variance but coarser grid",
    }


def local_median_floor(values: np.ndarray, train: int, guard: int) -> np.ndarray:
    floor = np.full(values.shape, np.nan, dtype=float)
    n = len(values)
    for i in range(n):
        left0 = max(0, i - guard - train)
        left1 = max(0, i - guard)
        right0 = min(n, i + guard + 1)
        right1 = min(n, i + guard + train + 1)
        samples = np.concatenate([values[left0:left1], values[right0:right1]])
        if samples.size:
            floor[i] = float(np.median(samples))
    fill = np.nanmedian(values)
    floor[~np.isfinite(floor)] = fill
    return np.maximum(floor, np.finfo(float).eps)


def model_cfar_fft(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    freqs, power = fft_spectrum(x, fs)
    mask = require_frequency_mask(freqs, cfg)
    idx_all = np.where(mask)[0]
    band_power = power[idx_all]
    floor = local_median_floor(band_power, cfg.cfar_train, cfg.cfar_guard)
    ratio = band_power / floor
    best_local = int(np.argmax(ratio))
    idx = idx_all[best_local]
    threshold = cfg.cfar_scale
    return {
        "detected": bool(ratio[best_local] >= threshold),
        "f0_hat": float(freqs[idx]),
        "score": float(ratio[best_local]),
        "threshold": float(threshold),
        "notes": "FFT peak selected by local median CFAR ratio",
    }


def glrt_stat_from_fft(x: np.ndarray, fs: float, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    y = preprocess(x)
    spec = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(len(y), d=1.0 / fs)
    sigma2 = float(np.var(y))
    # Approximate normalized projection energy for sine/cosine at FFT-bin frequencies.
    stat = 2.0 * (np.abs(spec) ** 2) / (len(y) * sigma2 + np.finfo(float).eps)
    return freqs, stat


GLRT_THRESHOLD_CACHE: dict[tuple[int, float, float, float, float, int, int], float] = {}


def estimate_glrt_threshold(n: int, fs: float, cfg: Config) -> float:
    key = (
        n,
        round(fs, 9),
        cfg.f_min,
        cfg.f_max,
        cfg.p_fa,
        cfg.glrt_mc,
        cfg.random_seed,
    )
    if key in GLRT_THRESHOLD_CACHE:
        return GLRT_THRESHOLD_CACHE[key]

    rng = np.random.default_rng(cfg.random_seed)
    maxima = np.empty(cfg.glrt_mc, dtype=float)
    for i in range(cfg.glrt_mc):
        noise = rng.normal(0.0, 1.0, n)
        freqs, stat = glrt_stat_from_fft(noise, fs, cfg)
        mask = require_frequency_mask(freqs, cfg)
        maxima[i] = float(np.max(stat[mask]))
    threshold = float(np.quantile(maxima, 1.0 - cfg.p_fa))
    GLRT_THRESHOLD_CACHE[key] = threshold
    return threshold


def model_glrt(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    freqs, stat = glrt_stat_from_fft(x, fs, cfg)
    mask = require_frequency_mask(freqs, cfg)
    idx = np.where(mask)[0][np.argmax(stat[mask])]
    threshold = estimate_glrt_threshold(len(x), fs, cfg)
    return {
        "detected": bool(stat[idx] >= threshold),
        "f0_hat": float(freqs[idx]),
        "score": float(stat[idx]),
        "threshold": threshold,
        "notes": f"matched-filter/GLRT with Monte Carlo P_FA={cfg.p_fa:g}",
    }


def diagonal_average(matrix: np.ndarray) -> np.ndarray:
    rows, cols = matrix.shape
    out = np.zeros(rows + cols - 1, dtype=float)
    counts = np.zeros_like(out)
    for i in range(rows):
        out[i : i + cols] += matrix[i, :]
        counts[i : i + cols] += 1.0
    return out / counts


def ssa_denoise(x: np.ndarray, window: int = 400, rank: int = 2) -> np.ndarray:
    y = preprocess(x)
    if window >= len(y) // 2:
        window = max(20, len(y) // 10)
    trajectory = np.lib.stride_tricks.sliding_window_view(y, window).T
    u, s, vt = randomized_svd(
        trajectory,
        n_components=rank,
        n_iter=3,
        random_state=0,
    )
    reconstructed = (u * s) @ vt
    return diagonal_average(reconstructed)


def model_ssa_fft(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    denoised = ssa_denoise(x)
    freqs, power = fft_spectrum(denoised, fs)
    mask = require_frequency_mask(freqs, cfg)
    idx = np.where(mask)[0][np.argmax(power[mask])]
    return {
        "detected": True,
        "f0_hat": float(freqs[idx]),
        "score": float(power[idx]),
        "threshold": np.nan,
        "notes": "rank-2 SSA reconstruction followed by FFT peak",
    }


def music_pseudospectrum(
    x: np.ndarray,
    fs: float,
    cfg: Config,
    embed_dim: int = 128,
    signal_dim: int = 2,
    grid_size: int = 12000,
) -> tuple[np.ndarray, np.ndarray]:
    y = preprocess(x)
    windows = np.lib.stride_tricks.sliding_window_view(y, embed_dim)
    step = max(1, len(windows) // 6000)
    sampled = windows[::step]
    sampled = sampled - sampled.mean(axis=0, keepdims=True)
    cov = sampled.T @ sampled / max(1, len(sampled))
    eigvals, eigvecs = np.linalg.eigh(cov)
    noise_space = eigvecs[:, : max(1, embed_dim - signal_dim)]
    freqs = np.linspace(cfg.f_min, cfg.f_max, grid_size)
    n = np.arange(embed_dim)
    pseudo = np.empty_like(freqs)
    for i, freq in enumerate(freqs):
        steering = np.exp(1j * 2.0 * np.pi * freq * n / fs)
        denom = np.linalg.norm(noise_space.conj().T @ steering) ** 2
        pseudo[i] = 1.0 / max(float(denom), np.finfo(float).eps)
    return freqs, pseudo


def model_music(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> dict:
    freqs, pseudo = music_pseudospectrum(x, fs, cfg)
    idx = int(np.argmax(pseudo))
    ratio = float(pseudo[idx] / np.median(pseudo))
    return {
        "detected": True,
        "f0_hat": float(freqs[idx]),
        "score": ratio,
        "threshold": np.nan,
        "notes": "MUSIC pseudospectrum with real sinusoid signal dimension 2",
    }


MODEL_FUNCS = [
    ("FFT Peak Baseline", model_fft_peak),
    ("Welch PSD", model_welch_psd),
    ("CFAR + FFT", model_cfar_fft),
    ("Matched Filter / GLRT", model_glrt),
    ("SSA Denoise + FFT", model_ssa_fft),
    ("MUSIC", model_music),
]


def run_real_data_models(t: np.ndarray, x: np.ndarray, fs: float, cfg: Config) -> pd.DataFrame:
    rows = []
    for name, func in MODEL_FUNCS:
        print(f"Running {name}...")
        rows.append(timed_model(name, func, t, x, fs, cfg))
    df = pd.DataFrame(rows)
    columns = [
        "model_name",
        "detected",
        "f0_hat",
        "f0_refined",
        "score",
        "threshold",
        "runtime_ms",
        "amplitude",
        "phase",
        "fit_rmse",
        "fit_explained_var",
        "notes",
    ]
    return df[columns]


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


def run_synthetic_evaluation(fs: float, n: int, cfg: Config) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.random_seed + 1)
    snr_values = [-20.0, -15.0, -12.0, -10.0, -5.0]
    f0 = 2.0
    amplitude = 0.035
    rows = []
    eval_n = min(n, 12000)
    # Use a smaller MC threshold in repeated simulation to keep runtime practical.
    sim_cfg = Config(**{**cfg.__dict__, "glrt_mc": max(60, min(cfg.glrt_mc, 100))})
    false_alarm_rate: dict[str, float] = {}

    print("Synthetic pure-noise false alarm check...")
    for name, func in MODEL_FUNCS:
        false_alarms = []
        for _ in range(cfg.sim_mc):
            noise_t = np.arange(eval_n, dtype=float) / fs
            noise_x = rng.normal(0.0, 1.0, eval_n)
            try:
                result = timed_model(name, func, noise_t, noise_x, fs, sim_cfg)
                false_alarms.append(bool(result["detected"]))
            except Exception as exc:
                print(f"  {name} failed in false-alarm simulation: {exc}")
                false_alarms.append(False)
        false_alarm_rate[name] = float(np.mean(false_alarms))

    for snr_db in snr_values:
        print(f"Synthetic SNR {snr_db:g} dB...")
        errors: dict[str, list[float]] = {name: [] for name, _ in MODEL_FUNCS}
        detections: dict[str, list[bool]] = {name: [] for name, _ in MODEL_FUNCS}
        for _ in range(cfg.sim_mc):
            sim_t, sim_x = synthetic_signal(fs, eval_n, f0, amplitude, snr_db, rng)
            for name, func in MODEL_FUNCS:
                try:
                    result = timed_model(name, func, sim_t, sim_x, fs, sim_cfg)
                    err = abs(float(result["f0_refined"]) - f0)
                    detected = bool(result["detected"]) and err <= 0.05
                except Exception as exc:
                    err = np.nan
                    detected = False
                    print(f"  {name} failed in simulation: {exc}")
                errors[name].append(err)
                detections[name].append(detected)

        for name, _ in MODEL_FUNCS:
            err_arr = np.asarray(errors[name], dtype=float)
            rows.append(
                {
                    "model_name": name,
                    "snr_db": snr_db,
                    "mean_abs_freq_error": float(np.nanmean(err_arr)),
                    "std_abs_freq_error": float(np.nanstd(err_arr)),
                    "p_detect_within_0_05hz": float(np.mean(detections[name])),
                    "p_false_alarm_noise_only": false_alarm_rate[name],
                    "mc_runs": cfg.sim_mc,
                    "sample_count": eval_n,
                }
            )
    return pd.DataFrame(rows)


def write_markdown_report(
    real_df: pd.DataFrame,
    sim_df: pd.DataFrame | None,
    cfg: Config,
    fs: float,
    n: int,
) -> None:
    lines = [
        "# Q1 多模型检测比较报告",
        "",
        f"- 数据源: `{cfg.data_path.name}` / sheet `{SHEET_SINGLE}`",
        f"- 样本数: `{n}`",
        f"- 采样率: `{fs:.6g} Hz`",
        f"- 频率搜索范围: `{cfg.f_min:g} - {cfg.f_max:g} Hz`",
        f"- GLRT 目标误报率: `{cfg.p_fa:g}`",
        "",
        "## 真实数据结果",
        "",
        real_df.to_markdown(index=False, floatfmt=".6g"),
        "",
    ]
    preferred_order = {
        "Matched Filter / GLRT": 0,
        "CFAR + FFT": 1,
        "FFT Peak Baseline": 2,
        "Welch PSD": 3,
        "SSA Denoise + FFT": 4,
        "MUSIC": 5,
    }
    ranked = real_df.copy()
    ranked["selection_priority"] = ranked["model_name"].map(preferred_order).fillna(99)
    best = ranked.sort_values(["detected", "selection_priority", "fit_rmse"], ascending=[False, True, True]).iloc[0]
    lines.extend(
        [
            "## 初步选择建议",
            "",
            (
                f"- 当前真实数据上，按 `detected=True`、可控误报/可解释判决优先排序，"
                f"`{best['model_name']}` 的精修频率为 `{best['f0_refined']:.8g} Hz`。"
            ),
            "- 后续若以正弦参数恢复为目标，优先考察 `Matched Filter / GLRT` 与 `CFAR + FFT`；它们的判决量更容易写入论文。",
            "- `FFT Peak Baseline` 作为传统方法基线保留；`SSA` 和 `MUSIC` 主要用于说明去噪增强和高分辨率方法的收益或参数敏感性。",
            "",
        ]
    )
    if sim_df is not None:
        lines.extend(
            [
                "## 合成数据 Monte Carlo",
                "",
                "默认合成验证为快速对照；如需论文级稳定统计，可增加 `--sim-mc` 和 `--glrt-mc`。",
                "",
                sim_df.to_markdown(index=False, floatfmt=".6g"),
                "",
            ]
        )
    (cfg.output_dir / "q1_model_compare_report.md").write_text("\n".join(lines), encoding="utf-8")


def plot_real_spectrum(t: np.ndarray, x: np.ndarray, fs: float, real_df: pd.DataFrame, cfg: Config) -> None:
    freqs, power = fft_spectrum(x, fs)
    mask = frequency_bounds(freqs, cfg)
    plt.figure(figsize=(10, 5))
    plt.semilogy(freqs[mask], power[mask], linewidth=1.0)
    for _, row in real_df.iterrows():
        plt.axvline(row["f0_refined"], linestyle="--", linewidth=0.9, alpha=0.75, label=row["model_name"])
    plt.xlabel("Frequency (Hz)")
    plt.ylabel("Power (log scale)")
    plt.title("Q1 single-source spectrum and model frequency estimates")
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_real_spectrum_estimates.png", dpi=180)
    plt.close()


def plot_model_scores(real_df: pd.DataFrame, cfg: Config) -> None:
    plt.figure(figsize=(10, 4.8))
    order = real_df.sort_values("fit_rmse")
    plt.bar(order["model_name"], order["fit_rmse"])
    plt.ylabel("Least-squares fit RMSE")
    plt.title("Q1 model comparison on real data")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_real_model_rmse.png", dpi=180)
    plt.close()


def plot_simulation(sim_df: pd.DataFrame, cfg: Config) -> None:
    plt.figure(figsize=(10, 5))
    for name, group in sim_df.groupby("model_name"):
        group = group.sort_values("snr_db")
        plt.plot(group["snr_db"], group["p_detect_within_0_05hz"], marker="o", label=name)
    plt.xlabel("SNR (dB)")
    plt.ylabel("Detection probability within 0.05 Hz")
    plt.title("Synthetic weak sinusoid detection probability")
    plt.ylim(-0.03, 1.03)
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(cfg.output_dir / "q1_synthetic_detection_probability.png", dpi=180)
    plt.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Q1 weak-signal detection models.")
    parser.add_argument("--data", type=Path, default=Path("data.xlsx"))
    parser.add_argument("--output-dir", type=Path, default=Path("q1_results"))
    parser.add_argument("--glrt-mc", type=int, default=200)
    parser.add_argument("--sim-mc", type=int, default=8)
    parser.add_argument("--skip-simulation", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config(
        data_path=args.data,
        output_dir=args.output_dir,
        glrt_mc=args.glrt_mc,
        sim_mc=args.sim_mc,
        run_simulation=not args.skip_simulation,
    )
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    t, x, fs = load_single_source(cfg.data_path)
    print(f"Loaded {cfg.data_path} / {SHEET_SINGLE}: N={len(x)}, fs={fs:.8g} Hz")

    real_df = run_real_data_models(t, x, fs, cfg)
    real_df.to_csv(cfg.output_dir / "q1_real_model_compare.csv", index=False, encoding="utf-8-sig")
    plot_real_spectrum(t, x, fs, real_df, cfg)
    plot_model_scores(real_df, cfg)

    sim_df = None
    if cfg.run_simulation:
        sim_df = run_synthetic_evaluation(fs, len(x), cfg)
        sim_df.to_csv(cfg.output_dir / "q1_synthetic_evaluation.csv", index=False, encoding="utf-8-sig")
        plot_simulation(sim_df, cfg)

    write_markdown_report(real_df, sim_df, cfg, fs, len(x))
    print("\nReal data comparison:")
    print(real_df.to_string(index=False))
    print(f"\nWrote outputs to: {cfg.output_dir.resolve()}")


if __name__ == "__main__":
    main()
