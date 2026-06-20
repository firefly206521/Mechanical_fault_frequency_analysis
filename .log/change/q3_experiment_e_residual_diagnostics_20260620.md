# Q3 实验组 E：残差诊断（#41）

## 范围与权威输入

- 目标：验证 Q3 四分量分离后剩余约 88% 方差是否呈现明显非正态或自相关结构。
- 原始数据：testA/data.xlsx 的多故障源工作表。
- 预处理：与 Q3 主程序一致，先做线性去趋势。
- 频率输入：只读取 q3_multisource_separation_results_optimized_complete/q3_detected_components.csv 中的 optimized 四频率，不重新检测、不混用其他目录。
- 联合频率：3.999998173832588、7.999928571466699、13.00008888535092、14.000023485389157 Hz。

## 方法

- 用四个固定频率的正弦、余弦列及常数项进行联合最小二乘拟合，残差定义为去趋势观测减联合拟合值。
- 偏度：标准化残差三阶中心矩。
- 峰度：报告原始峰度及超额峰度。
- 自相关：计算 0--100 阶有偏归一化样本 ACF；逐阶参考界使用 \(\pm1.96/\sqrt{N}\)。
- Ljung--Box：\(Q=N(N+2)\sum_{k=1}^{100}\rho_k^2/(N-k)\)，以自由度 100 的卡方分布计算右尾概率。
- 正态性：Jarque--Bera 检验，统计量 \(JB=N(S^2+K_e^2/4)/6\)，自由度为 2。
- 显著性水平：0.05。

## 运行命令

~~~powershell
C:\Users\Aupassen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m q3_multisource_separation.residual_diagnostics --data data.xlsx --components q3_multisource_separation_results_optimized_complete\q3_detected_components.csv --output-dir q3_multisource_separation_results_optimized_complete\q3_residual_diagnostics_experiment_e --max-lag 100
~~~

## 结果

- 样本量：40001；采样率：100 Hz。
- 残差标准差：0.099879860269563。
- 偏度：-0.014282955253016。
- 原始峰度：2.996354589901392；超额峰度：-0.003645410098608。
- 1--100 阶最大绝对 ACF：0.015421628078530，位于滞后 21 阶。
- 逐阶 95% 参考界：±0.009799877502297；超界滞后数：3。
- Ljung--Box：Q(100)=86.43070318678035，p=0.8312133693049204；不拒绝无自相关原假设。
- Jarque--Bera：JB=1.3822016505535164，p=0.50102422524855；不拒绝正态性。
- 四分量解释方差：0.11915160249147161（11.9152%）。

## 验证

- 新脚本通过 py_compile。
- 重建残差标准差与权威目录原 q3_residual_diagnostics.csv 完全一致。
- 重建解释方差与权威目录原结果完全一致。
- ACF 明细含 0--100 阶共 101 行；所有检验概率均位于 [0,1]。
- 输出目录包含完整指标、逐阶 ACF、逐点拟合/残差序列、ACF 图、Markdown 报告和可追溯元数据。

## 论文与问题记录

- paper/paper.tex 的 Q3 残差诊断已改为实跑值，并同时报告效应量、Ljung--Box 与 Jarque--Bera 结论。
- paper/review_issues.json 和根目录 review_issues.json 的 #41 已标记完成并指向本次结果目录。

## 限制与结论边界

在 5% 水平下，两项检验均未拒绝高斯白噪声近似。该结论不等于证明残差中绝对不存在微弱结构；尤其逐阶 ACF 有 3 个轻微超界点，论文中保留了这一事实及四分量仅解释 11.92% 总方差的限制说明。

## 下一步

如需提交论文终稿，可将本次 ACF 图纳入附录或正文，并在排版后编译检查交叉引用和图表位置。
