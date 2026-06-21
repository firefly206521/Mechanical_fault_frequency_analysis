# Experiment F: Q2 残差诊断 + GLRT 重扫描

> 日期：2026-06-20
> 触发：review_issues.json #26（Q2 白噪声诊断）、#48（残差 GLRT 重扫描）
> 覆盖 review issues: #26, #48 → completed

## 新建文件

| 文件 | 说明 |
|------|------|
| `q2_harmonic_recovery/experiment_f.py` | 独立实验脚本（~175 行） |
| `q2_experiment_f_results/q2_residual_diagnostics.csv` | 全部诊断统计量 |
| `q2_experiment_f_results/q2_residual_glrt_scan.csv` | GLRT 重扫描结果 |

## 实验设计

1. 从 `data.xlsx` 加载真实数据（单源故障）
2. 用 Q2 最终频率 2.0000016 Hz 做谐波拟合
3. 提取残差，计算全套诊断统计量
4. 对残差做 GLRT 全频段重扫描（P_FA=0.05, MC=500）

## 实验结果

| 指标 | 值 | 结论 |
|------|-----|------|
| 偏度 | -0.010 | 对称分布 ✓ |
| 超额峰度 | -0.009 | 无厚尾 ✓ |
| max\|ACF\| (1–100) | 0.0129 | 无显著自相关 ✓ |
| **Jarque-Bera** | stat=0.80, **p=0.669** | 正态性成立 ✓ |
| **Ljung-Box(100)** | Q=102.28, **p=0.418** | 白噪声 ✓ |
| **GLRT max T(f)** | 17.46 @ 18.53 Hz | **远低于门限 25.10** ✓ |

结论：去掉 2 Hz 成分后的残差是独立同分布高斯白噪声，不存在遗漏的周期性成分。

## 论文更新 (paper.tex)

- **L303**（Q2 模型充分性验证）：补充完整 JB/LB/GLRT 数值
- **L566–567**（噪声假设验证）：补充 Q2 JB=0.669, LB=0.418, Q3 JB 统计

## review_issues.json 更新

- `#26` (Q2 残差白噪声诊断) → `true`
- `#48` (Q2 残差 GLRT 重扫描确认无遗漏频率) → `true`
- 剩余未完成：#47（实验组 D）、#50（实验组 G）
