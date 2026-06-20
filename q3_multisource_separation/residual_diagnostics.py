"""Reproducible residual diagnostics for Q3 Experiment Group E."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

from q2_harmonic_recovery.core import linear_detrend
from q2_harmonic_recovery.outputs import line_svg, write_csv

from .core import load_multi_source, multi_harmonic_fit


def _chi2_survival(value: float, degrees_of_freedom: int) -> float:
    """Chi-square survival probability via regularized upper gamma."""
    if value < 0.0 or degrees_of_freedom <= 0:
        raise ValueError("invalid chi-square arguments")
    a = degrees_of_freedom / 2.0
    x = value / 2.0
    if x == 0.0:
        return 1.0
    eps, tiny, max_iterations = 1e-14, 1e-300, 10000
    if x < a + 1.0:
        term = 1.0 / a
        total = term
        ap = a
        for _ in range(max_iterations):
            ap += 1.0
            term *= x / ap
            total += term
            if abs(term) <= abs(total) * eps:
                break
        lower = total * math.exp(-x + a * math.log(x) - math.lgamma(a))
        return min(1.0, max(0.0, 1.0 - lower))
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / max(abs(b), tiny)
    h = d
    for index in range(1, max_iterations + 1):
        an = -index * (index - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) <= eps:
            break
    upper = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return min(1.0, max(0.0, upper))


def _acf(values: np.ndarray, max_lag: int) -> np.ndarray:
    centered = np.asarray(values, dtype=float) - float(np.mean(values))
    denominator = float(np.dot(centered, centered))
    if denominator <= 0.0:
        raise ValueError("residual variance must be positive")
    return np.asarray([
        1.0 if lag == 0 else float(np.dot(centered[:-lag], centered[lag:]) / denominator)
        for lag in range(max_lag + 1)
    ])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_commit(workspace: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=workspace, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def run(data_path: Path, components_path: Path, output_dir: Path, max_lag: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    frequencies = []
    with components_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            frequencies.append(float(row["frequency_hz"]))
    if len(frequencies) != 4:
        raise ValueError(f"expected four Q3 frequencies, found {len(frequencies)}")

    t, raw, fs = load_multi_source(data_path)
    y, trend = linear_detrend(t, raw)
    fit = multi_harmonic_fit(t, y, frequencies)
    residual = np.asarray(fit["residual"], dtype=float)
    n = len(residual)
    if max_lag >= n:
        raise ValueError("max_lag must be smaller than sample count")

    centered = residual - float(np.mean(residual))
    std = float(np.std(residual))
    z = centered / std
    skewness = float(np.mean(z ** 3))
    excess_kurtosis = float(np.mean(z ** 4) - 3.0)
    jarque_bera = float(n / 6.0 * (skewness ** 2 + excess_kurtosis ** 2 / 4.0))
    jarque_bera_p = math.exp(-jarque_bera / 2.0)  # chi-square df=2
    acf = _acf(residual, max_lag)
    lags = np.arange(1, max_lag + 1)
    ljung_box = float(n * (n + 2.0) * np.sum(acf[1:] ** 2 / (n - lags)))
    ljung_box_p = _chi2_survival(ljung_box, max_lag)
    confidence = 1.96 / math.sqrt(n)
    significant_lags = int(np.sum(np.abs(acf[1:]) > confidence))
    max_index = int(np.argmax(np.abs(acf[1:])) + 1)

    metrics = {
        "sample_count": n,
        "sampling_rate_hz": fs,
        "residual_mean": float(np.mean(residual)),
        "residual_std": std,
        "skewness": skewness,
        "raw_kurtosis": excess_kurtosis + 3.0,
        "excess_kurtosis": excess_kurtosis,
        "max_abs_acf_lag_1_100": float(abs(acf[max_index])),
        "max_abs_acf_lag": max_index,
        "acf_95pct_reference": confidence,
        "significant_acf_lags_1_100": significant_lags,
        "ljung_box_lag": max_lag,
        "ljung_box_q": ljung_box,
        "ljung_box_df": max_lag,
        "ljung_box_p_value": ljung_box_p,
        "jarque_bera_statistic": jarque_bera,
        "jarque_bera_df": 2,
        "jarque_bera_p_value": jarque_bera_p,
        "explained_variance": float(fit["explained_variance"]),
        "condition_design": float(fit["condition_design"]),
    }
    write_csv(output_dir / "q3_residual_diagnostics_full.csv", [metrics])
    acf_rows = [{
        "lag": int(lag),
        "acf": float(value),
        "reference_95_low": -confidence,
        "reference_95_high": confidence,
    } for lag, value in enumerate(acf)]
    write_csv(output_dir / "q3_residual_acf_lag_0_100.csv", acf_rows)
    series_rows = [{
        "time_s": float(time), "detrended_observation": float(observed),
        "fitted_four_component_signal": float(fitted), "residual": float(error),
    } for time, observed, fitted, error in zip(t, y, fit["fit"], residual)]
    write_csv(output_dir / "q3_residual_series.csv", series_rows)
    line_svg(
        output_dir / "q3_residual_acf_lag_1_100.svg",
        "Q3 四分量联合拟合残差自相关", "滞后阶数", "自相关系数",
        [
            ("残差 ACF", lags, acf[1:], "#1f77b4"),
            ("95%参考上界", lags, np.full(max_lag, confidence), "#d62728"),
            ("95%参考下界", lags, np.full(max_lag, -confidence), "#d62728"),
        ],
    )

    normality = "未拒绝正态性" if jarque_bera_p >= 0.05 else "拒绝正态性"
    whiteness = "未拒绝白噪声假设" if ljung_box_p >= 0.05 else "拒绝白噪声假设"
    report = f"""# Q3 实验组 E：残差诊断

## 数据与模型

- 数据：`{data_path}` 的多故障源工作表，线性去趋势后拟合。
- 频率：{', '.join(f'{value:.12g}' for value in frequencies)} Hz。
- 样本量：{n}；采样率：{fs:.12g} Hz；检验滞后：{max_lag} 阶。

## 结果

| 指标 | 数值 |
|---|---:|
| 残差标准差 | {std:.12g} |
| 偏度 | {skewness:.12g} |
| 超额峰度 | {excess_kurtosis:.12g} |
| 1--100 阶最大绝对自相关（滞后 {max_index}） | {abs(acf[max_index]):.12g} |
| 逐阶 95% 参考界 | ±{confidence:.12g} |
| 超出参考界的滞后数 | {significant_lags} |
| Ljung--Box Q({max_lag}) | {ljung_box:.12g} |
| Ljung--Box p 值 | {ljung_box_p:.12g} |
| Jarque--Bera 统计量 | {jarque_bera:.12g} |
| Jarque--Bera p 值 | {jarque_bera_p:.12g} |
| 四分量解释方差 | {fit['explained_variance']:.8%} |

在 5% 显著性水平下，Jarque--Bera 检验结论为“{normality}”，Ljung--Box 检验结论为“{whiteness}”。应同时报告效应量与 p 值：样本量很大时，即便单阶相关系数很小，联合白噪声检验也可能显著。
"""
    (output_dir / "q3_residual_diagnostics_report.md").write_text(report, encoding="utf-8")
    workspace = Path(__file__).resolve().parent.parent
    metadata = {
        "experiment": "Q3 Experiment Group E residual diagnostics (#41)",
        "data_path": str(data_path.resolve()),
        "data_sha256": _sha256(data_path),
        "components_path": str(components_path.resolve()),
        "components_sha256": _sha256(components_path),
        "frequencies_hz": frequencies,
        "preprocessing": "linear detrend identical to q3_multisource_separation.cli",
        "fit": "four-frequency simultaneous harmonic least squares",
        "tests": {"ljung_box_lag": max_lag, "normality": "Jarque-Bera"},
        "git_commit": _git_commit(workspace),
        "command": [sys.executable, *sys.argv],
    }
    (output_dir / "q3_residual_diagnostics_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-lag", type=int, default=100)
    args = parser.parse_args()
    metrics = run(args.data, args.components, args.output_dir, args.max_lag)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
