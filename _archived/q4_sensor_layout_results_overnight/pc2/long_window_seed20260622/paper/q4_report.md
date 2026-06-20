# 第四问：传感器布局与系统鲁棒性优化

## 1. 建模思想

题目没有给出设备几何、材料参数和真实传播路径，因此本文不假设可以计算连续空间中的物理全局最优坐标。第四问采用候选测点集合下的鲁棒布局优化：先给出有限个工程可安装位置，再用敏感度矩阵表示传播衰减、安装方向和局部耦合差异。

多传感器观测模型为

$$y_m(t)=\sum_k h_{mk}A_k\sin(2\pi f_kt+\phi_k+\delta_{mk})+n_m(t),$$

其中 $h_{mk}$ 为第 $m$ 个测点对第 $k$ 个故障源的综合敏感度，$\delta_{mk}$ 为传播相位差，$n_m(t)$ 为测点噪声。频率和振幅口径沿用第三问真实数据结果，故障频率约为 `4, 8, 13, 14 Hz`。

## 2. 融合检测与布局目标

每个测点在目标频率集合上计算 GLRT/匹配投影统计量，再按噪声方差倒数加权融合：

$$T_{\mathrm{fused}}(f)=\sum_{m\in S}w_mT_m(f),\qquad w_m\propto 1/\hat\sigma_m^2.$$

布局评分函数为

$$J(S)=\overline{P_D(S)}-2P_{FA}(S)-0.5\operatorname{Var}_k(P_{D,k}(S)).$$

该目标同时考虑平均检测概率、误报率和不同故障源检测均衡性。最多选择 3 个传感器，因此直接枚举全部 1、2、3 测点组合。

## 3. 敏感度矩阵

| 测点 | 4Hz | 8Hz | 13Hz | 14Hz |
|---|---:|---:|---:|---:|
| bearing_left | 0.95 | 0.65 | 0.35 | 0.45 |
| bearing_right | 0.60 | 0.95 | 0.45 | 0.50 |
| gearbox_left | 0.45 | 0.55 | 1.05 | 0.75 |
| gearbox_right | 0.40 | 0.50 | 0.80 | 1.10 |
| input_shaft | 1.10 | 0.45 | 0.35 | 0.25 |
| output_shaft | 0.35 | 0.50 | 0.65 | 1.00 |

## 4. 布局优化结果

综合评分最高的布局为 `bearing_left+bearing_right+gearbox_left`，其中三传感器最优布局为 `bearing_left+bearing_right+gearbox_left`。单传感器最优为 `gearbox_left`。

| 排名 | 布局 | 传感器数 | 平均检测概率 | 低SNR检测概率 | 平均误报率 | 均衡方差 | 评分 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | bearing_left+bearing_right+gearbox_left | 3 | 83.5% | 75.3% | 5.4% | 0.0277 | 0.7131 |
| 2 | bearing_right+gearbox_left+output_shaft | 3 | 82.2% | 73.4% | 5.1% | 0.0423 | 0.6991 |
| 3 | bearing_left+gearbox_left+output_shaft | 3 | 82.7% | 74.0% | 5.6% | 0.0342 | 0.6975 |
| 4 | bearing_left+gearbox_left+gearbox_right | 3 | 82.4% | 73.6% | 6.0% | 0.0317 | 0.6887 |
| 5 | bearing_left+gearbox_left | 2 | 80.4% | 70.6% | 5.3% | 0.0215 | 0.6878 |
| 6 | bearing_right+gearbox_left+input_shaft | 3 | 81.6% | 72.4% | 5.9% | 0.0261 | 0.6838 |
| 7 | bearing_left+gearbox_left+input_shaft | 3 | 81.9% | 72.8% | 6.2% | 0.0243 | 0.6824 |
| 8 | bearing_right+gearbox_left+gearbox_right | 3 | 81.5% | 72.2% | 5.7% | 0.0387 | 0.6816 |
| 9 | bearing_right+gearbox_left | 2 | 80.1% | 70.2% | 5.6% | 0.0285 | 0.6751 |
| 10 | bearing_left+bearing_right+output_shaft | 3 | 79.3% | 69.7% | 4.8% | 0.0624 | 0.6660 |

## 5. SNR 性能对比

| 对照组 | 布局 | SNR/dB | 平均故障源检测概率 | 全部故障检出率 | 误报率 |
|---|---|---:|---:|---:|---:|
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -25 | 43.8% | 0.6% | 4.7% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -20 | 76.0% | 17.1% | 2.8% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -15 | 96.9% | 87.5% | 5.5% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -12 | 99.9% | 99.7% | 5.6% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -10 | 100.0% | 100.0% | 5.1% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -5 | 100.0% | 100.0% | 5.1% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -25 | 33.6% | 0.3% | 6.3% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -20 | 74.1% | 16.5% | 4.4% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -15 | 93.8% | 75.3% | 4.9% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -12 | 99.7% | 98.9% | 6.3% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -10 | 100.0% | 100.0% | 5.2% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -5 | 100.0% | 100.0% | 5.4% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -25 | 24.9% | 0.0% | 4.8% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -20 | 62.6% | 3.1% | 4.8% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -15 | 78.2% | 13.5% | 3.8% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -12 | 86.2% | 44.7% | 4.5% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -10 | 90.8% | 63.3% | 5.0% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -5 | 99.9% | 99.4% | 4.2% |
| 单个最优测点 | gearbox_left | -25 | 17.4% | 0.4% | 5.3% |
| 单个最优测点 | gearbox_left | -20 | 42.0% | 1.8% | 5.2% |
| 单个最优测点 | gearbox_left | -15 | 80.7% | 37.5% | 5.7% |
| 单个最优测点 | gearbox_left | -12 | 96.8% | 87.4% | 5.2% |
| 单个最优测点 | gearbox_left | -10 | 98.8% | 95.3% | 3.8% |
| 单个最优测点 | gearbox_left | -5 | 100.0% | 100.0% | 5.8% |

## 6. 鲁棒性场景

| 场景 | 说明 | 最优布局 | 低SNR检测概率 | 平均误报率 |
|---|---|---|---:|---:|
| balanced | 敏感度和噪声相对均衡 | bearing_left+bearing_right+gearbox_left | 75.0% | 5.1% |
| spatial_noise_skew | 齿轮箱右侧和输入轴侧噪声明显偏大 | bearing_left+gearbox_left | 75.3% | 5.0% |
| weak_single_sensor | 部分测点安装耦合差或局部失敏 | bearing_left+bearing_right+gearbox_left | 75.0% | 5.1% |
| source_shadow | 部分故障源到若干测点传播衰减更强 | bearing_left+bearing_right+gearbox_left | 72.1% | 5.1% |

## 7. 结论

第四问的优化结果表明，在没有具体结构模型时，合理做法是把布局问题表述为候选测点集合上的鲁棒组合优化。最优三测点布局通常覆盖轴承座、齿轮箱壳体和轴端等互补位置，使不同故障源至少有一个高敏感度、低噪声测点可观测。与单测点相比，多传感器加权融合能提高低 SNR 下的综合检测概率，并降低局部失敏、噪声不均或相位抵消导致的漏检风险。

该结论不是物理连续空间的全局最优安装坐标，而是在给定候选测点、敏感度不确定场景和前三问检测模型下的鲁棒最优布局。
