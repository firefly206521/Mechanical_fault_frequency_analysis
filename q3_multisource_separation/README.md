# Q3 多故障源分离

本目录只包含第三问代码，不修改`q1_glrt`和`q2_harmonic_recovery`。

主模型使用多峰GLRT、联合谐波回归和BIC自动定阶；MUSIC用于近频辨识对照。输出图片直接复用第二问的白底、浅灰网格和PNG转换工具。

近频簇采用“细网格粗检、强分量剥离、残差复检、二源联合重拟合”。剥离只用于寻找弱分量初值，最终频率和模型选择仍由联合拟合完成，避免顺序误差传播。

Q1主模块导入时依赖Matplotlib，而当前Q2轻量运行环境没有该库。因此Q3在`core.py`中提供Q1兼容的GLRT统计量和Monte Carlo门限实现，公式与Q1一致，避免引入绘图库；Q1源码保持不变。

## 运行

在`shared_workspace`目录执行：

```powershell
python -m q3_multisource_separation.run_q3 --simulation-runs 200 --resolution-runs 200 --null-runs 500 --extreme-runs 100 --workers 8
```

也可以进入本目录执行：

```powershell
python run_q3.py --simulation-runs 200 --resolution-runs 200 --null-runs 500 --extreme-runs 100 --workers 8
```

追加到500次时使用：

```powershell
python run_q3.py --simulation-runs 500 --resolution-runs 500 --null-runs 500 --extreme-runs 100 --workers 8 --resume
```

`--resume`中的次数表示目标累计次数，程序只补做尚未存在的重复编号。每20次结果写入一次CSV，因此中断后可以继续。

续跑时程序会核对现有CSV表头。若代码升级新增或删除字段，会报`CSV schema mismatch`，此时应使用新输出目录重新运行，避免新旧字段错列。

## 主要判据

- 总体误报率0.05，最多10轮，单轮GLRT误报率取0.005；
- 新分量需要使BIC至少降低10；
- 联合最小二乘使用SVD，不计算正规矩阵的逆；
- 当设计矩阵条件数超过 $10^6$ 或数值秩不足时，结果标记为不可可靠辨识；
- 近频成功要求识别两个分量且两个频率误差均不超过频率间隔的四分之一。

详细结果说明由正式运行写入`q3_multisource_separation_results/q3_report.md`。

当前小规模基准为每个条件10次、纯噪声50次，总耗时约44秒。`q3_runtime.txt`分别记录真实数据分析、多源仿真、近频主模型、MUSIC和绘图耗时，并估算200次版本所需时间。

`q3_timing.csv`以结构化形式记录各阶段墙钟时间、调用次数和平均耗时，便于比较优化前后的性能。
