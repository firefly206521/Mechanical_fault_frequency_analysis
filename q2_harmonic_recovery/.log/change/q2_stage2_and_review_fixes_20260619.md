# 第二问阶段实现与审查完善日志

日期：2026-06-19

范围：`q2_harmonic_recovery/` 第二问单源故障波形恢复代码、审查修复和结果产物记录。

## 1. 阶段目标

第二问聚焦“单源故障”的波形恢复。第一问已经确定弱周期故障分量约为 2 Hz，因此第二问不再重新做多模型检测，而是在该频率附近恢复正弦故障波形，并验证恢复结果的稳定性、可信度和适用边界。

核心目标包括：

- 使用第一问频率作为初值，对全长 400 s 数据做谐波回归。
- 估计故障分量的频率、振幅、初相位和残差。
- 给出参数置信区间。
- 用分段拟合验证公共频率假设。
- 用针对性窄带滤波和 SSA 作为对照方法。
- 用合成数据验证频率、振幅、相位和波形恢复误差。
- 输出第二问报告、表格和图片。

## 2. 代码结构

第二问代码被组织为独立包：

- `q2_harmonic_recovery/run_q2.py`
  - 命令行入口。
  - 调用 `q2_harmonic_recovery.cli.main()`。
- `q2_harmonic_recovery/cli.py`
  - 解析参数。
  - 定位 `data.xlsx` 和第一问频率结果。
  - 串联数据读取、拟合、Bootstrap、分段验证、对照方法、仿真验证、文件输出。
- `q2_harmonic_recovery/core.py`
  - 数值计算部分。
  - 包含数据读取、线性去趋势、谐波拟合、频率精修、参数协方差、Bootstrap、分段联合拟合、窄带滤波、SSA、合成仿真等。
- `q2_harmonic_recovery/outputs.py`
  - 输出部分。
  - 包含 CSV、SVG/PNG 图片、Markdown 报告生成。
- `q2_harmonic_recovery/README.md`
  - 第二问模块说明和运行方式。

## 3. 主要算法流程

1. 读取 `data.xlsx` 中的 `单源故障` sheet。
2. 对原始信号做线性去趋势，得到预处理信号。
3. 读取第一问 GLRT 精修频率作为第二问初值。
4. 在初值附近做一维频率精修，使谐波回归残差平方和最小。
5. 估计模型：

   `s(t) = A sin(2πft + phi)`

6. 计算全局参数：
   - 频率
   - 振幅
   - 初相位
   - 残差标准差
   - 解释方差
   - 估计 SNR
   - 目标谱峰抑制

7. 使用局部线性化参数 Bootstrap 估计 95% 置信区间。
8. 将 400 s 数据按 25 s、50 s、100 s 做分段敏感性检查。
9. 比较公共频率模型和独立频率模型的 BIC。
10. 用针对性窄带滤波恢复 2 Hz 附近成分，与谐波回归对照。
11. 用 SSA 做数据驱动恢复对照。
12. 构造不同 SNR 的合成数据，验证恢复误差和置信区间覆盖率。
13. 输出报告、CSV 表格和图片。

## 4. 已生成的正式结果

正式输出目录：

`q2_harmonic_recovery_results/`

主要文件：

- `q2_report.md`
  - 第二问完整文字报告。
- `README.md`
  - 结果目录说明。
- `q2_global_parameters.csv`
  - 全局恢复参数。
- `q2_bootstrap_ci.csv`
  - 参数 Bootstrap 置信区间。
- `q2_joint_segment_fit.csv`
  - 50 s 分段拟合明细。
- `q2_joint_model_comparison.csv`
  - 公共频率模型与独立频率模型比较。
- `q2_joint_segment_fit_sensitivity.csv`
  - 不同分段长度明细。
- `q2_segment_length_sensitivity.csv`
  - 不同分段长度汇总。
- `q2_targeted_filter_comparison.csv`
  - 针对性窄带滤波对照。
- `q2_ssa_comparison.csv`
  - SSA 对照结果。
- `q2_simulation_validation.csv`
  - 合成仿真验证结果。
- `q2_runtime.txt`
  - 运行时间与关键参数记录。

主要图片：

- `q2_time_overlay_zoom.png`
- `q2_recovered_full.png`
- `q2_spectrum_comparison.png`
- `q2_spectrum_2hz_zoom.png`
- `q2_residual_diagnostics.png`
- `q2_segment_stability.png`
- `q2_segment_amplitude.png`
- `q2_segment_phase.png`
- `q2_segment_snr.png`
- `q2_segment_length_sensitivity.png`
- `q2_segment_bic_sensitivity.png`
- `q2_ssa_comparison.png`
- `q2_simulation_validation.png`

## 5. 阶段二核心结果

当前第二问主模型为谐波回归。小规模审查验证运行中得到的参数为：

- 频率：`2.000001615045 Hz`
- 振幅：`0.035190317`
- 初相位：`1.573555219 rad`
- 小规模验证运行 PNG 输出数量：`13`

正式结果以 `q2_harmonic_recovery_results/` 中的 CSV 和报告为准。

## 6. 审查报告来源

审查文件：

- `q2_harmonic_recovery/.log/review/code_review_20260619.json`
- `q2_harmonic_recovery/.log/review/code_review_20260619.md`

审查共列出 10 个问题：

- 高严重度：2 个
- 中严重度：6 个
- 低严重度：2 个

## 7. 审查后已完成修复

### 7.1 Bootstrap 相位 CI 边界问题

问题：

- 相位样本接近 `±π` 边界时，直接对 wrapped phase 做分位数会产生虚假窄区间。

修复：

- 在 `core.py` 中增加 `align_phase_to_reference()`。
- 将 Bootstrap 相位样本先平移到点估计附近的连续分支，再计算分位数。

### 7.2 相位覆盖率判断问题

问题：

- 仿真验证中相位覆盖率不能简单用 `wrap_phase(est - true)` 的误差侧判断。
- 否则大误差可能被折叠，低 SNR 下覆盖率虚高。

修复：

- 在 `core.py` 中增加 `phase_in_circular_ci()`。
- 对相位置信区间本身做圆环边界判断。
- 当 CI 跨越 `-π/π` 时，使用两段区间判断真值是否落入。

### 7.3 仿真频率硬编码问题

问题：

- `simulation_validation()` 原先硬编码 `f_true = 2.0`。
- 与真实数据精修频率存在不一致。

修复：

- `simulation_validation()` 增加 `f_true` 参数。
- `cli.py` 调用时传入 `fit["frequency_hz"]`。

### 7.4 Excel 数据有效性校验

问题：

- Excel 中空单元格、文本、NaN、Inf 可能静默进入后续计算。

修复：

- `load_single_source()` 对 `np.asarray(dtype=float)` 增加异常捕获。
- 增加 `np.isfinite()` 全数组检查。
- 非有限值报错时给出 Excel 单元格坐标。

### 7.5 BIC 的零残差保护

问题：

- 完美拟合或极小残差时可能触发 `math.log(0)`。

修复：

- BIC 计算使用 `math.log(max(sse / n, 1e-300))`。

### 7.6 SSA 窗口越界保护

问题：

- 短数据或降采样后，SSA 窗口可能大于信号长度。

修复：

- 调用 `_ssa_reconstruct_pair()` 前检查窗口长度。
- 无效窗口用 `warnings.warn()` 提醒并跳过。
- 如果没有任何有效 SSA 窗口，抛出明确 `ValueError`。

### 7.7 分段为空或短尾段处理

问题：

- 短数据可能导致全部分段被丢弃。
- 原实现可能继续计算并得到 NaN BIC。

修复：

- 若没有大于等于 10 s 的分段，直接抛出 `ValueError`。
- 对实质性短尾段给出 warning。
- 正常 40001 点数据最后多出的 1 个样本不再产生无意义 warning。

### 7.8 空分段绘图保护

问题：

- `joint_rows` 为空时，分段图绘制会对空数组求 min/max 并崩溃。

修复：

- `outputs.py` 中为 4 个分段图增加 `if joint_rows:` guard。
- 空数据时输出 warning 并跳过。
- `line_svg()` 对所有序列为空的情况也会跳过并输出 warning。

### 7.9 无 Chrome/Edge 时 PNG 转换保护

问题：

- 未找到浏览器时可能无 PNG 输出且删除 SVG。

修复：

- 无 Chrome/Edge 时输出 warning。
- 保留 SVG，不执行删除。

### 7.10 覆盖率验收阈值调整

问题：

- 200 次仿真下，覆盖率上界 `0.98` 过严，容易把正常 Monte Carlo 波动误报为失败。

修复：

- 只检查覆盖率是否低于 `0.90`。
- 不再因覆盖率略高于 `0.98` 判失败。

### 7.11 死代码清理

清理内容：

- 删除 `core.py` 中未使用的 `NormalDist` 导入和 `normal` 变量。
- 将 `outputs.py` 中函数体内 `NormalDist` 导入移到文件顶部。
- 将 `cli.py` 中未使用的 `envelope` 解包变量改为 `_`。

## 8. 验证记录

语法检查：

```powershell
python -m py_compile .\q2_harmonic_recovery\__init__.py .\q2_harmonic_recovery\core.py .\q2_harmonic_recovery\outputs.py .\q2_harmonic_recovery\cli.py .\q2_harmonic_recovery\run_q2.py
```

小规模完整流程验证：

```powershell
python .\q2_harmonic_recovery\run_q2.py --bootstrap-runs 200 --simulation-runs 3 --output-dir q2_harmonic_recovery_results_review_check2
```

相位圆环 CI 边界验证：

```powershell
python - <<'PY'
from q2_harmonic_recovery.core import phase_in_circular_ci
cases = [
    (3.10, -3.10, 0.20),
    (0.00, 3.00, 0.20),
    (2.90, 3.00, 0.20),
    (-2.90, 3.00, 0.20),
]
for value, center, half_width in cases:
    print(value, center, half_width, phase_in_circular_ci(value, center, half_width))
PY
```

预期结果：

- `3.10, -3.10, 0.20`：跨 `±π` 边界，判定覆盖。
- `0.00, 3.00, 0.20`：普通区间外，判定不覆盖。
- `2.90, 3.00, 0.20`：普通区间内，判定覆盖。
- `-2.90, 3.00, 0.20`：圆环域内仍在 CI 外，判定不覆盖。

空图和短数据边界检查：

- 完美正弦下 BIC 不再因 `log(0)` 崩溃。
- 全部分段过短时抛出明确 `ValueError`。
- SSA 所有窗口过长时抛出明确 `ValueError`。
- 空图输入不会生成坏图，也不会崩溃。

Diff 检查：

```powershell
git diff --check -- .\q2_harmonic_recovery\core.py .\q2_harmonic_recovery\outputs.py .\q2_harmonic_recovery\cli.py
```

结果：

- 无 whitespace error。
- PowerShell/Git 提示 LF/CRLF 转换 warning，不影响代码执行。

## 9. 当前注意事项

- 正式输出目录 `q2_harmonic_recovery_results/` 未在审查修复后重新全量生成。
- 审查验证使用了较小参数：
  - `--bootstrap-runs 200`
  - `--simulation-runs 3`
- 若需要最终提交论文用结果，建议用正式参数重新运行一次：

```powershell
python .\q2_harmonic_recovery\run_q2.py --bootstrap-runs 10000 --simulation-runs 200
```

- 默认完整运行可能耗时较长，但当前规模仍建议优先使用 CPU，不建议直接改 CUDA。
- 若第三问或后续阶段出现 15-40 分钟运行时间，应先做 profiling 和 CPU 并行评估，再决定是否使用 CUDA。

## 10. 结论

第二问已经形成完整的单源故障波形恢复链路：

- 主模型：谐波回归。
- 输入依据：第一问 GLRT 精修频率。
- 输出内容：参数估计、置信区间、分段稳定性、对照方法、仿真验证、报告和图片。
- 审查问题：10 个主要问题已处理，额外死代码问题也已清理。

当前代码更适合作为第二问最终写作和第三问扩展的基础。
