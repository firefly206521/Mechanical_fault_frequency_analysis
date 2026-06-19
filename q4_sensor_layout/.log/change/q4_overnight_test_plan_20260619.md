# Q4 夜间海量测试准备日志

日期：2026-06-19

## 目标

把第四问推进到可以长时间批量运行的状态。当前重点不是继续打磨论文文字，而是让两台电脑可以在夜间分别运行多组互补实验，并在第二天快速汇总排名稳定性、低 SNR 性能、误报率和评分函数敏感性。

## 已准备的入口

- 单次实验入口：`python -m q4_sensor_layout.run_q4`
- 夜间批量入口：`python -m q4_sensor_layout.run_q4_overnight --profile pc1|pc2|experimental`
- PowerShell 快捷脚本：
  - `q4_sensor_layout/run_overnight_pc1.ps1`
  - `q4_sensor_layout/run_overnight_pc2.ps1`
  - `q4_sensor_layout/run_overnight_experimental.ps1`
- 汇总入口：`python -m q4_sensor_layout.summarize_overnight --root-output q4_sensor_layout_results_overnight`

## 两台电脑推荐分工

### PC1

运行：

```powershell
.\q4_sensor_layout\run_overnight_pc1.ps1
```

包含：

- `baseline_long_seed20260619`：主口径长跑，验证当前默认模型。
- `low_snr_dense_seed20260621`：加密低 SNR 网格，观察检测概率转折区。
- `strict_false_alarm_seed20260623`：`P_FA=0.01`，验证严格误报控制下的布局变化。

### PC2

运行：

```powershell
.\q4_sensor_layout\run_overnight_pc2.ps1
```

包含：

- `baseline_repeat_seed20260620`：不同随机种子重复主口径，检查最优布局稳定性。
- `long_window_seed20260622`：`duration_s=80`，检查更长观测窗口的性能提升。
- `score_sensitivity_seed20260624`：提高误报和均衡惩罚，检查评分函数敏感性。

### 可选实验

若还有空闲机器或时间，运行：

```powershell
.\q4_sensor_layout\run_overnight_experimental.ps1
```

包含：

- `balanced_only_reference`：只跑均衡场景，作为理想传播条件参考。
- `shadow_and_noise_stress`：只跑空间噪声偏置和传播阴影场景，强调鲁棒性边界。

## 输出结构

每个作业都会输出到：

`q4_sensor_layout_results_overnight/<profile>/<job_name>/`

其中：

- `paper/`：论文可直接引用的报告、汇总表、图片。
- `raw/`：完整试验明细、全布局汇总和运行参数。

## 第二天汇总

所有机器结果合并到同一目录后运行：

```powershell
python -m q4_sensor_layout.summarize_overnight --root-output q4_sensor_layout_results_overnight
```

汇总结果会写入：

- `q4_sensor_layout_results_overnight/_summary/q4_overnight_job_summary.csv`
- `q4_sensor_layout_results_overnight/_summary/q4_overnight_top_layouts.csv`
- `q4_sensor_layout_results_overnight/_summary/q4_overnight_benchmark_snr.csv`

## 明天重点检查

- 不同随机种子的 Top 3 布局是否一致或高度重叠。
- 最优三传感器布局是否稳定优于单传感器和固定三传感器。
- 低 SNR 加密网格中检测概率拐点在哪里。
- 严格误报率下，最优布局是否发生明显变化。
- 更长观测窗口是否显著提高 `-20 dB` 到 `-12 dB` 的检测概率。
- 评分函数提高误报惩罚后，布局是否更偏向低噪声测点。

