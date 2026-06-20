# Q4 V1 自适应传感器布局报告

## 结果口径

本报告为 Q4 V1。V1 使用参数化结构示例和自适应候选网格来选择最多 3 个传感器位置；坐标是无量纲模型坐标，不是真实设备安装坐标。Q4 V0 的权威过夜结果仍位于 `q4_sensor_layout_results_overnight/`，在 V1 中只作为有限候选区域基线参考。

## 模型

候选测点由可安装表面网格生成。每个测点记录区域、坐标、安装方向、噪声水平和对约 `4, 8, 13, 14 Hz` 故障频率的复响应。布局目标采用白化响应下的非中心参数：

$$\lambda_k(S)=A_k^2 h_{S,k}^H \Sigma_S^{-1} h_{S,k}.$$

V1 优先最大化最弱故障源的融合 GLRT 代理检测能力。代理量先按照噪声方差给每个传感器加权，再计算每个故障频率的等效非中心参数，因此比单纯累加白化响应更接近后续 Monte Carlo 检测器。

当前目标函数权重为：`detection_mean_lambda=0.1`，`trace_info=0.002`，`min_eigen=0.002`，`scaled_redundancy=-0.03`。其中冗余惩罚按融合检测强度缩放，不再使用绝对无量纲惩罚。

Monte Carlo 验证排序权重为：`pd=0.45`，`low_snr=0.35`，`min_pd=0.2`，`fa_excess=-2.0`。

## 搜索流程

1. 生成 V1 参数化候选点。
2. 用单点白化响应和噪声水平预筛选。
3. 用 greedy 选点，再用 one-swap 局部搜索修正。
4. 在小规模候选集上执行完整枚举，验证 greedy + swap 的目标差距。
5. 只对前若干布局和基线布局运行 GLRT Monte Carlo。

## 当前运行

- profile: `smoke`
- grid size: `36`
- response gain jitter: `0.1`
- response phase jitter: `0.1`
- response jitter mode: `sensor`
- noise correlation: `0.2`
- prescreen count: `20`
- greedy+swap 到完整枚举最优的相对差距: `0.000000`
- 最优 V1 布局: `v1_p026+v1_p021+v1_p018`
- 最优 V1 区域: `gearbox_zone_left+gearbox_zone_right+bearing_zone_left`
- 最优目标值: `0.000110751`
- Monte Carlo 验证最优布局: `v1_p015+v1_p021+v1_p026`
- Monte Carlo 验证最优区域: `gearbox_zone_right+gearbox_zone_right+gearbox_zone_left`
- Monte Carlo 验证分数: `0.362500`

## 结论

V1 给出了“参数化结构示例下的稳定区域选择方法”。解析目标用于快速缩小候选布局，Monte Carlo 验证排序用于最终比较候选布局在检测率、低 SNR 表现、最弱源平衡和误报率上的综合表现。若后续有真实设备几何、有限元频响或移动传感器标定数据，只需要替换候选点响应矩阵和噪声协方差，布局搜索与 Monte Carlo 验证流程可以保持不变。

## 限制

- 当前坐标不代表真实机器坐标。
- 当前传播响应是简化参数化模型，不是有限元模型。
- smoke 结果只用于验证流程；是否进入论文主线需要 medium 或 official 结果支持。
