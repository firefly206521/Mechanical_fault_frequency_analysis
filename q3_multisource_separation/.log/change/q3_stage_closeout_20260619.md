# Q3 阶段收尾日志

## 收尾目标

本阶段完成第三问的工作区整理和文档收口：

- 保留优化版正式结果。
- 保留优化前正式基线用于对比。
- 归档旧中间结果目录。
- 删除 Python 缓存。
- 输出论文材料和工程收尾记录。
- 不修改核心算法，不重新运行大型实验。

## 当前权威结果

第三问当前权威结果目录为：

```text
E:\AIworkspace\2026CSU-math\testA\q3_multisource_separation_results_optimized
```

该目录包含：

- `q3_report.md`
- `q3_runtime.txt`
- `q3_simulation_validation.csv`
- `q3_resolution_limit.csv`
- `q3_extreme_summary.csv`
- `q3_optimization_report.md`
- `q3_timing.csv`
- 相关 PNG 图表

优化前正式基线目录保留为：

```text
E:\AIworkspace\2026CSU-math\testA\q3_multisource_separation_results_review_fixed_large
```

用途是支撑优化对比，不作为最终论文主结果。

## 归档策略

旧中间结果目录归档到：

```text
E:\AIworkspace\2026CSU-math\testA\q3_archived_results_20260619
```

计划归档目录：

- `q3_multisource_separation_results`
- `q3_multisource_separation_results_mid`
- `q3_multisource_separation_results_mid_parallel`
- `q3_multisource_separation_results_final`

这些目录保留为历史追溯，但不再作为第三问最终结论来源。

## 最终运行命令

优化版正式运行命令：

```powershell
python -m q3_multisource_separation.run_q3 --simulation-runs 200 --resolution-runs 200 --null-runs 500 --extreme-runs 100 --workers 8 --output-dir q3_multisource_separation_results_optimized
```

运行统计：

| 指标 | 数值 |
|---|---:|
| simulation target runs | 200 |
| resolution target runs | 200 |
| null target runs | 500 |
| extreme target runs | 100 |
| workers | 8 |
| simulation completed rows | 1000 |
| resolution completed rows | 4800 |
| null completed rows | 500 |
| extreme completed rows | 900 |
| empirical false alarm rate | 0.002 |
| equal amplitude empirical limit | 0.002 Hz |
| unequal amplitude empirical limit | 0.003 Hz |
| total seconds | 522.356337 |
| estimated full seconds | 519.312860 |

## 真实数据结果

优化版真实数据自动识别 4 个故障分量：

| 分量 | 频率/Hz | 振幅 | 初相位/rad | 分量 SNR/dB |
|---:|---:|---:|---:|---:|
| 1 | 3.999998174 | 0.019103 | 1.371555 | -17.378 |
| 2 | 7.999928571 | 0.024889 | -2.989028 | -15.080 |
| 3 | 13.000088885 | 0.010503 | -2.157736 | -22.574 |
| 4 | 14.000023485 | 0.040053 | 0.112468 | -10.947 |

可在论文中概括为识别出约 `4, 8, 13, 14 Hz` 四个潜在故障频率。

## 仿真与误报

| 总 SNR/dB | K 识别正确率 | 说明 |
|---:|---:|---|
| -20 | 1.5% | 极低信噪比下不稳定 |
| -15 | 76.0% | 过渡区 |
| -12 | 98.0% | 基本稳定 |
| -10 | 100.0% | 稳定 |
| -5 | 100.0% | 稳定 |

纯噪声顺序检测经验误报率为 `0.20%`。

## 近频与优化对比

优化报告显示：

- 等幅 `0.0025 Hz` 成功率由 `91.0%` 提升至 `100.0%`。
- 不等幅 `0.003 Hz` 成功率由 `87.0%` 提升至 `97.5%`。
- 完全同频正确不拆分率由 `98.0%` 提升至 `100.0%`。
- 纯噪声误报保持为 `1/500` 到 `1/500`，没有增加。
- 实际数据仍识别约 `4, 8, 13, 14 Hz` 四个故障源。
- 优化版总运行时间为 `522.4 s`，约为基线 `275.7 s` 的 `1.89` 倍。

当前近频结论：

- 等幅经验辨识极限约为 `0.002 Hz`。
- 不等幅经验辨识极限约为 `0.003 Hz`。
- MUSIC 可作为对照方法，但不等幅近频下明显弱于主模型。

## 已知限制

- Hessian 频率区间未经过 Bootstrap 校准，只能作为局部不确定性诊断。
- 不等幅 `0.003 Hz` 的 Hessian 区间覆盖率约 `72.7%`，不能称为严格 95% 置信区间。
- 完全同频与强相消场景在单通道下不具备唯一分解条件，成功标准是不误拆成两个稳定独立源。
- `overcomplete_k8` 能稳定识别，但运行时间明显增加。
- 当前模型针对正弦叠加故障特征；若后续题目扩展到冲击调制或明显非平稳信号，需要另加包络谱、循环平稳或时频方法。

## 后续建议

第三问不建议继续改核心算法。若需要补充实验，只建议小范围追加：

1. 不等幅 `0.003 Hz` 近频从 200 次追加到 500 次，验证 `97.5%` 结论稳定性。
2. 等幅 `0.002 Hz` 近频从 200 次追加到 500 次，巩固经验极限边界。
3. 其余表格可直接采用优化版结果。

如果进入第四问，应重点使用第三问的两个结论：

- 单通道可在本题数据中稳定识别多源周期故障。
- 单通道在完全同频、相消和极低 SNR 下存在不可辨识或低检出边界，因此多传感器布局能提升鲁棒性。
