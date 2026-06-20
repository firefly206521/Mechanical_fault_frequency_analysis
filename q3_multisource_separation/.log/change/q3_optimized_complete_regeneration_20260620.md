# Q3 optimized 统一结果补跑记录

## 范围

- 以 `q3_multisource_separation_results_optimized` 为算法与历史数据基线。
- 新建 `q3_multisource_separation_results_optimized_complete`，不覆盖旧目录。
- 补齐 13 个 SNR 水平，并新增 `harmonic_pair` 极端工况。
- 保留原 optimized 近频、纯噪声、真实数据和其他极端工况试验。

## 参数与假设

- 随机种子：`20260620`。
- SNR/dB：`-22,-20,-18,-16,-15,-14,-12,-10,-8,-6,-4,-2,0`。
- 每个 SNR：200 次；新增 9 个水平，共补跑 1800 次。
- 近频：沿用 optimized 原定义，2 个振幅场景 × 12 个间隔 × 200 次，共 4800 条。
- `harmonic_pair`：频率 4 Hz 和 8 Hz，振幅 0.019103 和 0.024889，噪声标准差取真实数据残差估计，100 次。
- 同频和相消成功标准：不误拆为两个稳定分量；相消允许估计 0 或 1 个可观测分量。

## 命令

```powershell
python -m q3_multisource_separation.run_q3 `
  --simulation-runs 200 --resolution-runs 200 `
  --null-runs 500 --extreme-runs 100 --workers 8 `
  --resume --skip-resolution --skip-null `
  --output-dir q3_multisource_separation_results_optimized_complete
```

## 关键结果

- SNR=-15 dB：正确分量数识别率 76.0%。
- SNR=-12 dB：正确分量数识别率 98.0%。
- 等幅 0.0025 Hz：成功率 100.0%。
- 不等幅 0.003 Hz：成功率 97.5%。
- 同频、相消、谐波对：成功率均为 100.0%。
- 经验界限：等幅约 0.002 Hz，不等幅约 0.003 Hz。

## 验证覆盖

- SNR 汇总 13 行，每行 200 次并带 Wilson 95% 区间。
- 近频原始试验 4800 条，无重复 `(amplitude_case, separation_hz, replicate)` 键。
- 极端工况 10 类 × 100 次，共 1000 条。
- 版本、命令、参数和随机种子记录在 `q3_run_metadata.json`。

## 已知限制

- 纯噪声 0.20% 是首步 GLRT 扫描误报率，不代表完整 SIC+BIC 流程的最终过估率。
- 经验近频界限依赖当前记录长度、噪声、振幅比和相位分布。
- 4 Hz/8 Hz 被识别为两个周期分量，不据此断言存在两个物理故障源。
