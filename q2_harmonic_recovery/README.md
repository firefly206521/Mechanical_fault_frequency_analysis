# Q2 谐波回归波形恢复

本目录只包含第二问代码，不修改或覆盖 `q1_glrt` 与 `q1_glrt_results`。

运行：

```powershell
python run_q2.py --bootstrap-runs 10000 --simulation-runs 200
```

程序自动读取相邻 `q1_glrt_results/q1_glrt_result.csv` 的第一问精修频率，并在找不到工作区内 `data.xlsx` 时读取上级赛题目录中的数据。

输出写入相邻的 `q2_harmonic_recovery_results`。Bootstrap采用完整40001点数据的局部线性化参数法；多信噪比仿真也使用完整40001点，并重新生成时域数据、估计频率、振幅和相位。

程序还包含两项稳健性分析：

- SSA对照：测试原始500、1000和2000点窗口，在降采样后的数据中提取2 Hz附近的成对SSA分量；
- 分段长度敏感性：比较25秒、50秒和100秒分段下的频率偏差、振幅变异和公共频率BIC优势。

绘图采用与第一问一致的白底、浅灰网格和蓝/红/灰配色。程序先生成矢量图，再自动调用本机Chrome或Edge渲染为PNG；结果目录不保留SVG。
