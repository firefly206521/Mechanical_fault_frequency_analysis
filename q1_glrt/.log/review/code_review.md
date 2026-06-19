# Q1 GLRT 代码审查报告

> **审查日期:** 2026-06-19  
> **审查范围:** `q1_glrt\` (含依赖 `q1_model_compare.py`)  
> **审查强度:** high (7 angles, verified)

---

## 总结

| 类别 | 数量 | 涉及发现 |
|------|------|----------|
| 正确性缺陷 | 3 | #1, #2, #3 |
| 性能浪费 | 2 | #4, #9 |
| 代码重复 | 1 | #5 |
| 可维护性 | 4 | #6, #7, #8, #10 |

**最优先修复:** #1 — 删除多余 `preprocess()` 调用，消除管线不一致。

---

## #1 双重线性去趋势导致管线不一致

- **文件:** `q1_glrt/core.py`
- **行号:** 38, 69, 91（以及 `outputs.py:130`）
- **严重度:** 中

### 说明

`run_glrt_q1`、`glrt_detect_signal`、`fft_peak_detect_signal` 在调用
`glrt_stat_from_fft` / `fft_spectrum` 之前先执行了 `preprocess(x)`，
而这些函数内部也会调用 `preprocess()`。

### 后果

- 实际数据的 GLRT 统计量经过**双重去趋势**计算
- 阈值校准 (`estimate_glrt_threshold`) 传入原始噪声，仅**单次去趋势**
- 两条管线不一致。若 `preprocess` 未来改为非幂等操作（非线性滤波等），
  检测统计量与阈值将系统性偏离

### 建议

删除调用方多余的 `preprocess(x)`，统一由底层函数内部预处理。

---

## #2 `np.argmax` 在空数组上崩溃

- **文件:** `q1_glrt/core.py`（以及 `q1_model_compare.py`）
- **行号:** 94（`q1_model_compare.py:148,169,199,255,295`）
- **严重度:** 中

### 说明

模式 `np.where(mask)[0][np.argmax(power[mask])]` 在 `mask` 全为 `False` 时，
`power[mask]` 为空数组，`np.argmax([])` 抛出 `ValueError`。

### 触发条件

- 用户配置 `--f-min` 高于 `--f-max`
- 频率网格与 `[f_min, f_max]` 无交集
  （如 `--f-min=50 --f-max=60`，`fs=100`，Nyquist=50，`rfftfreq` 无 >50 的 bin）

### 建议

在 `argmax` 前检查 `mask` 是否有 `True`，无则给出明确错误提示。

---

## #3 SNR 计算中 `math.log10(0.0)` 触发 `ValueError`

- **文件:** `q1_glrt/core.py`
- **行号:** 124
- **严重度:** 中低

### 说明

```python
estimated_snr_db = 10.0 * math.log10(signal_power / residual_power)
```

- `signal_power = 0` → `math.log10(0.0)` 抛出 `ValueError`（Python 3.x）
- `residual_power = 0` → `signal_power / 0.0` 抛出 `ZeroDivisionError`

### 触发条件

- 提取信号振幅为 0（`signal_power = 0`）
- 完美正弦拟合（`residual_power = 0`）

均为极值场景，但会导致 `analyze_preprocessing_and_noise` 整体崩溃。

### 建议

对 `signal_power` 或 `residual_power <= 0` 做保护，返回 `NaN` 或标记为无意义。

---

## #4 `load_single_source` 同一文件被重读 7 次

- **文件:** `q1_glrt/core.py`, `q1_glrt/outputs.py`
- **行号:** `core.py:36,118,160`; `outputs.py:48,129,163,180`
- **严重度:** 中（性能）

### 说明

一次 `cli.py main()` 运行中，`load_single_source(cfg.data_path)` 在 7 个位置被独立调用：

| # | 调用位置 | 文件:行号 |
|---|----------|-----------|
| 1 | `run_glrt_q1` | `core.py:36` |
| 2 | `analyze_preprocessing_and_noise` | `core.py:118` |
| 3 | `run_segment_validation` | `core.py:160` |
| 4 | `plot_noise_analysis` | `outputs.py:48` |
| 5 | `plot_glrt_statistic` | `outputs.py:129` |
| 6 | `plot_fft_baseline` | `outputs.py:163` |
| 7 | `plot_recovered_signal` | `outputs.py:180` |

每次调用均执行 `pd.read_excel` + 列验证 + 时间轴校验，对大文件显著拖慢。

### 建议

`main()` 中加载一次 `(t, x, fs)`，作为参数传递给下游函数。

---

## #5 `synthetic_signal` 函数完全重复

- **文件:** `q1_glrt/core.py:187-201` 与 `q1_model_compare.py:377-391`
- **严重度:** 低

### 说明

两处定义逐字相同（14 行，相同参数、相同逻辑）。
`q1_glrt/core.py` 已从 `q1_model_compare` 导入 8 个符号，不存在依赖隔离的理由。

### 建议

删除 `core.py` 中的本地定义，改为：

```python
from q1_model_compare import synthetic_signal
```

---

## #6 `run_glrt_q1` 与 `glrt_detect_signal` 返回字典键名不一致

- **文件:** `q1_glrt/core.py`
- **行号:** 50-63 vs 78-87
- **严重度:** 低

### 说明

| 语义 | `run_glrt_q1` 键名 | `glrt_detect_signal` 键名 |
|------|--------------------|----------------------------|
| 统计量 | `glrt_score` | `score` |
| 幅值 | `amplitude_for_reference` | `amplitude` |
| 相位 | `phase_for_reference_rad` | `phase` |

语义相同但键名不同，混用会导致 `KeyError`。

### 建议

统一键名，或将 `glrt_detect_signal` 改为 `run_glrt_q1` 的内部子函数。

---

## #7 `GLRT_PARAMETERS` 死代码

- **文件:** `q1_glrt/core.py`
- **行号:** 24-32
- **严重度:** 低

### 说明

模块级字典 `GLRT_PARAMETERS` 定义后从未在 `q1_glrt` 或 `q1_model_compare`
中被引用。9 行死代码占据命名空间，信息与 `build_parameter_table()` 重复，
维护时易遗漏导致过时信息残留。

### 建议

删除或合并到 `build_parameter_table()` 中作为文档字符串。

---

## #8 参考频率 2.0 Hz 硬编码

- **文件:** `q1_glrt/core.py:181`, `q1_glrt/outputs.py:82`
- **严重度:** 低

### 说明

- `run_segment_validation`: `"frequency_error_from_2hz"` 列写死 `2.0`
- `plot_segment_validation`: 参考红线写死 `2.0`

若真实故障频率不同，误差列失去意义，图中参考线产生误导，且无警告。

### 建议

通过 `Config` 或 CLI 参数化（如 `--expected-frequency`）。

---

## #9 分段循环内无意义 `Config` 克隆

- **文件:** `q1_glrt/core.py`
- **行号:** 169
- **严重度:** 低

### 说明

```python
Config(**{**cfg.__dict__, "output_dir": cfg.output_dir})
```

覆盖 `output_dir` 为相同值，属于完全无操作的克隆。
每段产生一次无意义内存分配与 `__dict__` 拆解。
且 `glrt_detect_signal` 根本不使用 `output_dir` 字段。

### 建议

直接传入 `cfg`，或至少将克隆提升到循环外。

---

## #10 `configure_plot_fonts` 全局状态泄漏

- **文件:** `q1_glrt/outputs.py`
- **行号:** 23-29
- **严重度:** 低

### 说明

`configure_plot_fonts()` 无条件设置 `plt.rcParams["font.sans-serif"]` 和
`plt.rcParams["axes.unicode_minus"]`，无保存/恢复，无上下文管理器。
`cli.main()` 开头调用后，整个进程的 matplotlib 全局配置被永久改变。

### 建议

使用 `plt.rc_context()` 上下文管理器限制作用域，或在无中文字体的系统上给出 warning。
