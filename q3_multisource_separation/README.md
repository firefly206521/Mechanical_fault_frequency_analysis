# Q3 多故障源分离

本目录只包含第三问代码，不修改 `q1_glrt` 和 `q2_harmonic_recovery`。

主模型使用多峰 GLRT、联合谐波回归和 BIC 自动定阶；MUSIC 用于近频辨识对照。近频簇采用“细网格粗检、强分量剥离、残差复检、二源联合重拟合”。剥离只用于寻找弱分量初值，最终频率和模型选择仍由联合拟合完成。

## 正式结果

当前第三问权威结果目录为：

```text
q3_results
```

优化前正式基线目录为：

```text
q3_multisource_separation_results_review_fixed_large
```

旧中间结果已归档到：

```text
q3_archived_results_20260619
```

论文材料和阶段收尾日志位于：

```text
q3_multisource_separation/.log/change/q3_paper_materials_20260619.md
q3_multisource_separation/.log/change/q3_stage_closeout_20260619.md
```

## 运行

从 `testA` 目录执行正式复验：

```powershell
python -m q3_multisource_separation.run_q3 --simulation-runs 200 --resolution-runs 200 --null-runs 500 --extreme-runs 100 --workers 8 --output-dir q3_results
```

也可以进入本目录执行：

```powershell
python run_q3.py --simulation-runs 200 --resolution-runs 200 --null-runs 500 --extreme-runs 100 --workers 8
```

`--resume` 中的次数表示目标累计次数，程序只补做尚未存在的重复编号。每 20 条结果写入一次 CSV，因此中断后可以继续。

## 主要判据

- 总体目标误报率为 0.05，最多 10 轮，单轮 GLRT 误报率取 0.005。
- 新分量需要使 BIC 至少降低 10。
- 联合最小二乘使用 SVD，不计算正规矩阵的逆。
- 当设计矩阵条件数超过 $10^6$ 或数值秩不足时，结果标记为不可靠辨识。
- 近频成功要求识别两个分量，且两个频率误差均不超过真实间隔的四分之一。
- Hessian 频率区间仅作为局部不确定性诊断，不能称为严格 95% 置信区间。

优化版正式结果：真实数据识别约 `4, 8, 13, 14 Hz` 四个故障源；纯噪声经验误报率约 `0.20%`；等幅近频经验辨识极限约 `0.002 Hz`，不等幅近频经验辨识极限约 `0.003 Hz`。
