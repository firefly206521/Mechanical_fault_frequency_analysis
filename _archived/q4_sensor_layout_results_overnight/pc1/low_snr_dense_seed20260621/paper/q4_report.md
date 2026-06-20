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
| 1 | bearing_left+bearing_right+gearbox_left | 3 | 34.3% | 34.3% | 4.6% | 0.0506 | 0.2251 |
| 2 | bearing_left+gearbox_left+output_shaft | 3 | 35.0% | 35.0% | 4.6% | 0.0728 | 0.2227 |
| 3 | bearing_left+bearing_right+output_shaft | 3 | 35.5% | 35.5% | 4.7% | 0.0783 | 0.2220 |
| 4 | bearing_left+gearbox_left+gearbox_right | 3 | 32.2% | 32.2% | 4.2% | 0.0594 | 0.2081 |
| 5 | bearing_right+gearbox_left+output_shaft | 3 | 34.7% | 34.7% | 5.2% | 0.0837 | 0.2012 |
| 6 | bearing_left+gearbox_left+input_shaft | 3 | 32.7% | 32.7% | 5.6% | 0.0422 | 0.1937 |
| 7 | bearing_right+gearbox_left+input_shaft | 3 | 31.9% | 31.9% | 5.2% | 0.0465 | 0.1919 |
| 8 | gearbox_left+input_shaft+output_shaft | 3 | 32.3% | 32.3% | 4.9% | 0.0716 | 0.1894 |
| 9 | bearing_left+gearbox_right+output_shaft | 3 | 33.0% | 33.0% | 5.0% | 0.0822 | 0.1889 |
| 10 | bearing_right+gearbox_left+gearbox_right | 3 | 32.5% | 32.5% | 5.2% | 0.0702 | 0.1869 |

## 5. SNR 性能对比

| 对照组 | 布局 | SNR/dB | 平均故障源检测概率 | 全部故障检出率 | 误报率 |
|---|---|---:|---:|---:|---:|
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -30 | 6.9% | 0.0% | 6.0% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -28 | 14.1% | 0.0% | 5.8% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -25 | 26.8% | 0.0% | 7.6% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -22 | 40.5% | 0.3% | 5.6% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -20 | 60.7% | 5.7% | 6.9% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -18 | 74.0% | 12.3% | 6.9% |
| 全部测点参考 | bearing_left+bearing_right+gearbox_left+gearbox_right+input_shaft+output_shaft | -15 | 86.6% | 47.2% | 7.2% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -30 | 3.6% | 0.0% | 4.4% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -28 | 6.5% | 0.0% | 4.8% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -25 | 10.9% | 0.0% | 4.9% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -22 | 26.9% | 0.0% | 4.8% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -20 | 45.9% | 1.8% | 4.6% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -18 | 65.8% | 5.2% | 4.3% |
| 最优三测点 | bearing_left+bearing_right+gearbox_left | -15 | 80.7% | 26.8% | 4.6% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -30 | 3.1% | 0.0% | 4.7% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -28 | 5.6% | 0.0% | 6.7% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -25 | 10.7% | 0.0% | 5.7% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -22 | 20.7% | 0.0% | 5.8% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -20 | 38.1% | 0.4% | 4.6% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -18 | 56.9% | 1.0% | 5.0% |
| 随机三测点 | bearing_left+gearbox_right+input_shaft | -15 | 73.1% | 6.8% | 6.0% |
| 单个最优测点 | gearbox_left | -30 | 3.2% | 0.0% | 5.3% |
| 单个最优测点 | gearbox_left | -28 | 6.9% | 0.0% | 6.0% |
| 单个最优测点 | gearbox_left | -25 | 10.6% | 0.0% | 8.7% |
| 单个最优测点 | gearbox_left | -22 | 17.0% | 0.0% | 5.1% |
| 单个最优测点 | gearbox_left | -20 | 29.0% | 0.0% | 5.1% |
| 单个最优测点 | gearbox_left | -18 | 41.7% | 1.5% | 5.6% |
| 单个最优测点 | gearbox_left | -15 | 57.7% | 6.3% | 7.9% |

## 6. 鲁棒性场景

| 场景 | 说明 | 最优布局 | 低SNR检测概率 | 平均误报率 |
|---|---|---|---:|---:|
| balanced | 敏感度和噪声相对均衡 | bearing_left+gearbox_left+gearbox_right | 35.2% | 4.4% |
| spatial_noise_skew | 齿轮箱右侧和输入轴侧噪声明显偏大 | bearing_left+gearbox_left+output_shaft | 38.3% | 4.3% |
| weak_single_sensor | 部分测点安装耦合差或局部失敏 | bearing_left+bearing_right+gearbox_left | 34.8% | 4.6% |
| source_shadow | 部分故障源到若干测点传播衰减更强 | bearing_left+bearing_right+output_shaft | 33.5% | 4.5% |

## 7. 结论

第四问的优化结果表明，在没有具体结构模型时，合理做法是把布局问题表述为候选测点集合上的鲁棒组合优化。最优三测点布局通常覆盖轴承座、齿轮箱壳体和轴端等互补位置，使不同故障源至少有一个高敏感度、低噪声测点可观测。与单测点相比，多传感器加权融合能提高低 SNR 下的综合检测概率，并降低局部失敏、噪声不均或相位抵消导致的漏检风险。

该结论不是物理连续空间的全局最优安装坐标，而是在给定候选测点、敏感度不确定场景和前三问检测模型下的鲁棒最优布局。
