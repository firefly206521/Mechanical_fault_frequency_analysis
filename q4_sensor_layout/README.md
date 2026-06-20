# Q4 传感器布局与系统鲁棒性优化

本模块用于第四问 V0：在候选测点集合中选择最多 3 个加速度传感器，使多故障源检测概率高、误报率低，并对不同故障源保持均衡敏感。

V0 的结论是“候选区域集合下的鲁棒最优布局”，不是未知真实设备连续物理空间中的全局最优安装坐标。候选点名称如 `bearing_left`、`gearbox_left`、`output_shaft` 表示抽象安装区域及其敏感度/噪声假设。

单次运行示例：

```powershell
python -m q4_sensor_layout.run_q4 --runs 20 --false-alarm-runs 50 --threshold-mc 100
```

正式运行可使用默认参数：

```powershell
python -m q4_sensor_layout.run_q4
```

夜间批量运行：

```powershell
.\q4_sensor_layout\run_overnight_pc1.ps1
.\q4_sensor_layout\run_overnight_pc2.ps1
```

批量结果汇总：

```powershell
python -m q4_sensor_layout.summarize_overnight --root-output q4_sensor_layout_results_overnight
```

输出目录默认为 `q4_sensor_layout_results/`。其中 `paper/` 放论文材料，`raw/` 放完整枚举、运行参数和 Monte Carlo 明细。夜间批量结果默认写入 `q4_sensor_layout_results_overnight/<profile>/<job_name>/`。

由于题目没有给出机械结构几何和传播路径，本模块采用“候选测点 + 敏感度矩阵 + 噪声场景集”的鲁棒建模方式，不声称得到连续物理空间中的全局最优坐标。

当前 V0 权威长测结果位于 `q4_sensor_layout_results_overnight/`，汇总表位于 `q4_sensor_layout_results_overnight/_summary/`。主推荐布局为 `bearing_left+gearbox_left+output_shaft`，低 SNR 和长窗口口径下的近似等价备选为 `bearing_left+bearing_right+gearbox_left`。
