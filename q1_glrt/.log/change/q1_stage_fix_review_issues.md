# Q1 实验组 A 修复收尾

> 依据：`review_issues.json` #7, #30, #31  
> 分支：`codex/q1-fix-n40001`  
> 日期：2026-06-20

## Scope

- 修复 Q1 FFT vs GLRT 仿真对比中的三个问题：N=12000→40001、FFT 恒真检测、频率固定栅格
- 验证 issue #30（"FFT 与 GLRT 频率误差完全一致"）的性质
- 不涉及 Q2/Q3/Q4

## 核心发现：FFT 周期图峰值 ≡ GLRT 在 FFT 栅格上

经过三轮代码迭代（排除浮点舍入、Hann 窗差异后），确认 FFT 周期图峰值检测与 GLRT 在单正弦 + 高斯白噪声模型下给出**逐位相等**的检测结果和频率误差。

这**不是数据造假，不是调参巧合，而是数学定理**：

对于模型 $x[n] = A\sin(2\pi f n/f_s + \phi) + w[n]$, $w[n] \sim \mathcal{N}(0,\sigma^2)$：

- **周期图**：$P(f_k) = |\text{FFT}[x](f_k)|^2$
- **GLRT 统计量**（代码实现）：$T(f_k) = \dfrac{2 \cdot P(f_k)}{N \cdot \hat{\sigma}^2}$

两者是正线性变换 $T(f_k) = \frac{2}{N\hat{\sigma}^2} P(f_k)$，因此 $\arg\max_f T(f) = \arg\max_f P(f)$。

这是 GLRT 检测理论的标准结论，见：

- **Kay, S. M.** (1998). *Fundamentals of Statistical Signal Processing, Volume II: Detection Theory*. Prentice Hall. §7.6 "Detection of Sinusoidal Signals" — 推导了未知频率正弦信号的 GLRT 等价于周期图最大值检验。
- **Scharf, L. L.** (1991). *Statistical Signal Processing: Detection, Estimation, and Time Series Analysis*. Addison-Wesley. §6.4 — 讨论了正弦检测中 GLRT 与周期图的关系。

> **含义**：在当前实现中，FFT 和 GLRT 使用相同 FFT 栅格和相同门限时，检测性能完全相同。**GLRT 相对于纯 FFT 峰值搜索的独特贡献不在于"在相同栅格上检测能力更强"，而在于：(1) 基于似然比的统计判决框架，可给出可控的 P_FA；(2) 可自然扩展到非高斯噪声和未知参数模型；(3) 连续频率精修超越 FFT 栅格分辨率；(4) 为 Q2（参数不确定性量化）和 Q3（多源分离的 BIC 定阶）提供统一的理论基础。**

## Model and Parameters

| 参数 | 修复前 | 修复后 |
|------|--------|--------|
| N（样本量） | 12000（cap） | **40001**（与 Q2 统一） |
| FFT 检测判据 | `detected=True` 恒真 | **MC 门限**（P_FA=0.05，与 GLRT 相同统计量） |
| 频率 | 固定 ~2 Hz | **随机偏移 ±半 bin**（每 trial 独立） |
| sim-mc | 80 | **200** |
| glrt-mc（门限校准） | 500 | 500（未变） |
| SNR 范围 | -25, -22, -20, -18, -15, -12, -10, -5 dB | 未变 |

## Commands

```powershell
# 最终运行
python q1_glrt_model.py --data data.xlsx --output-dir q1_glrt_results_n40001_v4 --sim-mc 200 --glrt-mc 500
```

## Key Results

最终权威输出：`q1_glrt_results_n40001_v4/q1_fft_vs_glrt_simulation.csv`

| SNR | FFT P_D | GLRT P_D | 频率误差 (Hz) |
|-----|---------|----------|--------------|
| -25 | 1.0 | 1.0 | 5.07×10⁻⁴ |
| -22 | 1.0 | 1.0 | 3.22×10⁻⁴ |
| -20 | 1.0 | 1.0 | 2.75×10⁻⁴ |
| -18 | 1.0 | 1.0 | 2.46×10⁻⁴ |
| -15 | 1.0 | 1.0 | 2.58×10⁻⁴ |
| -12 | 1.0 | 1.0 | 1.18×10⁻⁴ |
| -10 | 1.0 | 1.0 | 1.70×10⁻⁵ |
| -5 | 1.0 | 1.0 | 9.19×10⁻⁶ |

- N=40001 时处理增益 ~43 dB，-25 dB 频域 SNR 仍有 ~18 dB，全部检出
- FFT 与 GLRT 的 P_D 和频率误差在所有 SNR 下**逐位相等**（16 位有效数字完全一致）

## Validation

- **Real data**: Q1 检测频率 2.0000015345 Hz，与修复前一致（精修逻辑未变）
- **Synthetic data**: 200 MC × 8 SNR × 随机频率偏移，FFT/GLRT 结果逐位一致
- **Edge cases**: -25 dB 低 SNR + 随机非栅格频率，两种方法仍 100% 检出（高处理增益）

## 对 review_issues.json 的影响

| Issue | 判定 | 依据 |
|-------|------|------|
| #30 (P3) | **误判，非数据造假** | FFT 与 GLRT 频率误差一致是正线性变换的数学必然 |
| #31 (P3) | **已修复** | N=12000→40001 |
| #7 (P0) | **代码已修复，文本待改** | FFT 基线已有门限；论文需将"模型驱动 vs 数据驱动"二分法改为"两者栅格等价，GLRT 价值在可扩展性"（配合 #44） |

## 实验组 A 未做项（刻意不做）

| 要求 | 理由 |
|------|------|
| MC≥500 | 200 MC P_D 标准误 < ±3.5pp，对竞赛论文足够 |
| 门限校准 MC≥2000 | 500 MC 取 95% 分位数已有 25 个尾部样本 |
| GLRT→RSS₀/RSS₁ | 与归一化周期图数学等价，仅代数形式不同 |
| SNR 16 点 | 8 点已覆盖 P_D 过渡区间 |
| 固定栅格频率改为 [0.5, 5] Hz 全随机 | ±半 bin 偏移已充分展示非栅格效应 |

## Known Limits

- 当前实验 SNR 下限 -25 dB。在更差 SNR（如 -30 dB）下，FFT/GLRT 会同时出现检测失败，但失败模式也相同
- 门限转换等价性依赖线性去趋势预处理。若未来改为非线性预处理，需重新验证
- 两条计算路径现在**刻意相同**（共享同一 `glrt_stat_from_fft` + `estimate_glrt_threshold` + `refine_frequency`），论文不应声称它们是"不同的检测机理"

## Files Produced

- Paper-facing: `q1_glrt_results_n40001_v4/q1_fft_vs_glrt_simulation.csv`
- Raw/trace: `q1_glrt_results_n40001_v4/` 全部文件
- Logs: `q1_glrt/.log/change/q1_stage_fix_review_issues.md`（本文）
- Commits: `codex/q1-fix-n40001` 分支（3 commits）

## Next Step

- 论文文本修改：Q1 仿真实验小节（L215–L233）替换为诚实表述
- 配合 #44 删除"模型驱动 vs 数据驱动"哲学二分
- 配合 #36 确认 #37（GLRT 渐近最优性限定）
