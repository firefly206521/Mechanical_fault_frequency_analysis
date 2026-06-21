# 最终审查修订日志（2026-06-20）

## 权威口径

- Q4 唯一权威版本：`q4_sensor_layout_v1_results_robustness_v2_medium`。
- 最终布局采用 Monte Carlo 验证最优 `v1_p105+v1_p074+v1_p062`，验证分数 `0.522010`。
- `v1_p105+v1_p074+v1_p098`仅是解析目标最优，不作为论文最终布局。
- Q3 统一使用 `q3_multisource_separation_results_optimized_complete`，实验 C/D 使用 `q3_experiment_results/c` 与 `q3_experiment_results/d`。

## 完成的修订

- 按 `paper/final_review_issues.json` 的 R1--R30 修订论文，并将30项 `completed` 全部设为 `true`。
- 重写 Q4：区分解析筛选目标与 Monte Carlo 验证评分，补充120点候选模型、传播响应、噪声相关性、扰动参数、搜索规模、Wilson区间及局限性。
- 重绘 Q4 最终布局图和性能曲线，明确使用 V1 验证最优 `p105+p074+p062`：
  - `q4_sensor_layout_v1_results_robustness_v2_medium/paper/q4_v1_validated_layout_heatmap.png`
  - `q4_sensor_layout_v1_results_robustness_v2_medium/paper/q4_v1_validated_pd_snr_curve.png`
- 修正 Q1 中 FFT 与 GLRT 的等价关系、实际统计量定义和 Monte Carlo 门限表述。
- 为 Q2 补充合成数据误差/覆盖率表，区分真实数据残差与合成真值误差。
- 为 Q3 补充完整流程误报率、实验 D 条件化辨识界限、极端工况参数及正确条件数定义。
- 收窄参数敏感性结论：仅支持当前真实数据附近的局部稳定性，不覆盖低 SNR 或近频判决边界；未为 R19 新增实验。
- 修正图片路径、附录真实文件路径、符号冲突、过度措辞、表格排版和未使用字体定义。

## 实验决策

- 本轮没有重新运行 Q1--Q4 Monte Carlo 实验。
- 原因：R1--R30所需数据均已存在；R19通过收窄结论而非补做边界敏感性实验解决。
- Q4 两张新图由既有 V1 CSV 重绘，不改变任何实验结果。

## 验证

- `paper/final_review_issues.json`：UTF-8 JSON解析成功，30项均为 `completed=true`。
- 编译：XeLaTeX → BibTeX → XeLaTeX × 2。
- 输出：`paper/paper.pdf`，A4，共27页。
- 最终日志中无未定义引用、无 overfull/underfull box。
- 已渲染抽查 Q4 页17--21及附录第27页；图、表、公式和长路径无裁切或重叠。
- LaTeX封装脚本因本机 TeX Live 2026 的 `latexmk` 启动故障未能使用，随后直接调用 XeLaTeX/BibTeX 完成同等编译流程。
