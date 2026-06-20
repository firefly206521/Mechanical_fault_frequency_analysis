# 第三问结果说明

本目录保存“多故障源分离与定位”的小规模基准结果。当前版本用于检查代码和运行性能，尚未执行每个条件200次的正式Monte Carlo实验。

## 当前运行规模

- 多源恢复实验：5个SNR，每个条件10次，共50次；
- 近频辨识实验：12个间隔、2种振幅条件，每个条件10次，共240次；
- 纯噪声误报实验：50次；
- GLRT门限Monte Carlo：100次；
- 随机种子：`20260620`。

10次实验只能用于检查程序趋势，不能作为最终辨识概率。`q3_resolution_limit.csv`中的经验极限是初步结果，正式论文应追加更多次数后再引用。

## 真实数据结果

程序没有预设故障频率，自动识别出4个分量：

| 分量 | 频率/Hz | 振幅 | 初相位/rad | 分量SNR/dB |
|---:|---:|---:|---:|---:|
| 1 | 3.999998 | 0.019103 | 1.371542 | -17.378 |
| 2 | 7.999929 | 0.024889 | -2.989236 | -15.080 |
| 3 | 13.000089 | 0.010503 | -2.157351 | -22.574 |
| 4 | 14.000024 | 0.040053 | 0.111600 | -10.947 |

联合模型的总估计SNR约为-8.69 dB。设计矩阵条件数约为1.00015，真实数据中的4个分量不存在明显病态问题。

## 表格文件

- `q3_global_parameters.csv`：数据规模、分量数、总SNR和全局诊断；
- `q3_detected_components.csv`：4个分量的频率、振幅、相位和逐分量SNR；
- `q3_model_selection.csv`：逐轮GLRT、BIC和停止原因；
- `q3_condition_diagnostics.csv`：设计矩阵条件数、奇异值和数值秩；
- `q3_segment_stability.csv`：8个50秒段的参数稳定性；
- `q3_residual_diagnostics.csv`：残差分布和解释方差；
- `q3_simulation_trials.csv`：50次多源仿真逐次结果；
- `q3_simulation_validation.csv`：按SNR汇总的识别率和条件误差；
- `q3_resolution_trials.csv`：240次近频试验逐次结果；
- `q3_resolution_limit.csv`：辨识概率、Wilson区间和条件数汇总；
- `q3_music_comparison.csv`：主模型与MUSIC辨识率对照；
- `q3_null_trials.csv`：纯噪声误报试验；
- `q3_runtime.txt`：各阶段实测耗时与200次版本预计耗时。

## 图片文件

- `q3_time_separated_components.png`：前10秒原始信号与4个恢复分量；
- `q3_spectrum_before_after.png`：分离前和联合残差频谱；
- `q3_model_selection.png`：自动增加分量时的BIC改善；
- `q3_residual_diagnostics.png`：残差分布、自相关和Q-Q图；
- `q3_segment_frequency_stability.png`：50秒分段频率偏差；
- `q3_simulation_order_accuracy.png`：不同总SNR下的故障源数量识别率；
- `q3_simulation_errors.png`：频率误差和波形RMSE；
- `q3_resolution_probability.png`：主模型和MUSIC的近频成功率；
- `q3_condition_vs_separation.png`：条件数随频率间隔的变化。

## 实测耗时

本次小规模运行约44秒。详细分解见`q3_runtime.txt`。按照逐次平均耗时线性外推，每个条件200次的完整版本约需12分钟；实际时间会受CPU负载和数值优化迭代次数影响。

## 后续追加

代码检查完成后，可在`q3_multisource_separation`目录执行：

```powershell
python run_q3.py --simulation-runs 200 --resolution-runs 200 --null-runs 500 --glrt-mc 500 --resume
```

`--resume`会保留现有重复编号，只补做尚未完成的试验。达到200次后，程序会重新生成汇总CSV、PNG和报告。

