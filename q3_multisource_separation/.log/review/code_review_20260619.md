# Q3 多源分离代码审查报告

**审查日期**: 2026-06-19
**审查范围**: q3_multisource_separation/ 全部源文件 (core.py, cli.py, experiments.py, outputs.py, run_q3.py, __init__.py)
**审查强度**: xhigh — 9 个独立角度并行扫描
**审查方法**: 多角度并行发现 → 交叉验证 → 去重合成

---

## 总览

| 严重级别 | 数量 |
|---|---|
| 🔴 CRITICAL — 错误结果或崩溃 | 7 |
| 🟠 HIGH — 架构/设计不一致 | 4 |
| 🟡 MEDIUM — 健壮性/可维护性 | 6 |
| 🔵 LOW — 效率/代码复用 | 5 |
| **合计** | **22** |

---

## 🔴 严重缺陷

### B1. MUSIC 导向矢量使用绝对时间代替采样周期

- **文件**: core.py:531
- **发现角度**: A(逐行bug扫描) / C(跨文件追踪) / E(wrapper正确性) — **3个独立角度同时命中**

core.py:513 丢弃了 baseband_series 返回的采样率 fsb:
```python
tb, z, _ = baseband_series(t, x, center_hz)
```

core.py:531 用 tb[1]（绝对时间）代替采样周期:
```python
steering = np.exp(1j * 2.0 * np.pi * np.arange(order)[:, None] * tb[1] * grid[None, :])
```

**问题**: `tb[1]` = `t[0] + Ts`，而不是 `Ts`。当 `t[0] != 0` 时，导向矢量中的相位项为 `n * (t[0] + Ts) * grid_val` 而非正确的 `n * Ts * grid_val`，引入频变相位失真，MUSIC 伪谱峰值系统性偏移。`close_pair_resolver` 正确地使用了 `fsb`；MUSIC 因用 `_` 丢弃返回值而无法获得正确采样周期。

**触发条件**: 任何时间轴不从零开始的数据集。

**修复**:
- Line 513: `tb, z, fsb = baseband_series(t, x, center_hz)`
- Line 531: 用 `1.0 / fsb` 或 `tb[1] - tb[0]` 代替 `tb[1]`

---

### B2. golden_minimize 在频带边界收到 hi < lo

- **文件**: core.py:402-403 及 core.py:409-410
- **发现角度**: A / E — 2个独立角度

```python
left_hi = min(values[1] - 1e-7, 0.012)
values[0] = golden_minimize(objective, -0.012, left_hi, iterations=18)
```

**问题**: 当 `values[1]` 精确等于 `-0.012`（基带下边界）时，`left_hi = min(-0.012 - 1e-7, 0.012) = -0.0120000001`。此时 `lo = -0.012 > hi = -0.0120000001`，即 `hi < lo`。golden_minimize 中 `(hi - lo)` 为负，导致黄金分割点计算错误，搜索退化为在区间外评估目标函数并返回无意义的中间值。

**对称问题**: Line 409-410 当 `values[0]` 漂移到 `+0.012` 时同样存在。

**触发条件**: 频率偏移在坐标下降后漂移到基带边界 `+/-0.012 Hz`。

**修复**: 在 golden_minimize 内部或调用前添加 `if hi <= lo: return (lo + hi) / 2.0` 保护。

---

### B3. argmax 在空掩码上返回索引 0

- **文件**: core.py:449
- **发现角度**: A

```python
allowed = np.abs(residual_grid - one_frequency) >= exclusion
residual_index = int(np.argmax(np.where(allowed, residual_power, -np.inf)))
```

**问题**: 当 `exclusion` 覆盖了基带内所有网格点时，`allowed` 全为 `False`，`np.argmax` 在全 `-np.inf` 数组上返回索引 `0`——即基带左边界的一个无意义频率。该频率被当作"第二个峰值"，可能触发虚假二源检测。

**修复**: 在 argmax 后检查 `np.any(allowed)` 或 `residual_power[residual_index] > -np.inf`。

---

### B4. GLRT 统计量校正与阈值标定不匹配

- **文件**: core.py:211
- **发现角度**: I (架构)

```python
corrected = statistic * max(len(residual) - fitted_parameter_count, 1) / len(residual)
```

**问题**: 阈值 `cfg.threshold` 通过对**未校正**统计量 Monte Carlo 标定得到（cli.py:170）。但实际比较的是乘以 `(N - k) / N` 的**校正后**统计量。校正因子 `<= 1`，有效检验比名义 `p_fa` 更保守。在 `detect_multitone` 中 `fitted_parameter_count = 3k + 1` 随分量数增长，后期迭代比前期更保守——误报率不均匀。

**影响**: 零假设误报率实验（只做单次 `fitted_parameter_count=1`）测得的误报率不能反映多迭代检测器的真实行为。

**修复**: 阈值标定时使用与检测一致的校正公式。

---

### B5. Workbook 资源泄漏 + 工作表索引越界

- **文件**: core.py:65-68
- **发现角度**: D (Python陷阱)

```python
wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
ws = wb["多故障源"] if "多故障源" in wb.sheetnames else wb.worksheets[1]
rows = [(row[0], row[1]) for row in ws.iter_rows(min_row=2, values_only=True)]
wb.close()
```

**问题**:
1. 若 `"多故障源"` 不存在且 Workbook 只有 1 个工作表，则 `wb.worksheets[1]` 抛出 `IndexError`，`wb.close()` 不执行，句柄泄漏。
2. 无 `try/finally` 或 context manager 保护——任何异常都会导致泄漏。

**修复**: 使用 `with` 语句或 `try/finally`；对 `wb.worksheets` 索引做边界检查。

---

### B6. segment_series 条件初始化 — NameError 风险

- **文件**: outputs.py:105-107
- **发现角度**: A / C / G — 3个独立角度

```python
if component_id == 1:
    segment_series = []
segment_series.append(...)  # NameError 若 component_id 不是从 1 开始
```

**修复**: 在循环前显式初始化 `segment_series = []`。

---

### B7. condition_series 条件初始化 — NameError 风险

- **文件**: outputs.py:129-131
- **发现角度**: A / G

```python
if case == "equal":
    condition_series = []
condition_series.append(...)  # NameError 若 "equal" 不是首迭代
```

**修复**: 在循环前显式初始化 `condition_series = []`。

---

## 🟠 高级别架构问题

### A1. detect_multitone 不路由到 close_pair_resolver

- **文件**: core.py:278-279
- **发现角度**: E

注释称 "Close-pair experiments use their dedicated exhaustive split resolver below"，但 `detect_multitone` **从不调用** `close_pair_resolver`。真实数据主分析路径使用坐标下降，近频分辨率实验使用专用的 `close_pair_resolver`。真实数据近频对由更简单的管线处理，分辨率实验的成功率**高估**了主分析对近频的实际分离能力。

**修复**: 在 `detect_multitone` 中检测疑似近频对（间距 < 某阈值）并路由到 `close_pair_resolver`。

---

### A2. 两套平行检测算法

- **文件**: experiments.py:56-78 vs core.py:242-304
- **发现角度**: C / E / I — 3个独立角度

| 特性 | detect_multitone (真实数据) | fast_spaced_detection (仿真) |
|---|---|---|
| 候选生成 | 分裂 + 残差峰，全量评估 | 仅残差峰单点添加 |
| 精修策略 | 全频联合坐标下降 | 仅精修新增频率 |
| BIC 阈值 | 参数化 `bic_delta` | 硬编码 `10.0` |
| 历史记录 | 完整迭代历史 | 无历史 |

仿真验证使用的是**不同**于真实数据管线的算法。对主分析的修改不会自动传播到仿真路径。

**修复**: `fast_spaced_detection` 复用 `detect_multitone` 核心循环，或提取共享逻辑。

---

### A3. close_pair_resolver 混用两个拟合域

- **文件**: core.py:485-486
- **发现角度**: E / I

```python
improvement = one["bic"] - two["bic"]          # 复数基带 BIC（降采样）
accepted = ... and not full_fit["ill_conditioned"]  # 实数全速率条件数
```

BIC 来自降采样数据复指数拟合，条件数来自原始数据实数正弦拟合。复数 BIC 用 `2*len(z)` 样本，实数 BIC 用 `len(y)`。同一 `10.0` 阈值在两个域含义不同。

**修复**: 统一使用实数域 `multi_harmonic_fit` 的 BIC 和条件数。

---

### A4. _multi_sse / _complex_sse 丢弃 lstsq 秩信息

- **文件**: core.py:151, core.py:383
- **发现角度**: E

```python
beta = np.linalg.lstsq(design, y, rcond=1e-12)[0]  # 丢弃 rank
```

频率接近时设计矩阵近似秩亏。`lstsq` 返回最小范数解，SSE 面在退化方向平坦。golden_minimize 可能收敛到虚假局部极小值。

**修复**: 检查秩；秩亏时添加正则化或提前终止优化。

---

## 🟡 中等级别问题

### M1. 汇总函数中的浮点相等比较
- **文件**: experiments.py:359, 387
- `float(row["snr_total_db"]) == snr` 和 `float(row["separation_hz"]) == separation` 用 `==` 比较浮点数。分离值 `0.00025` 等无精确二进制表示。
- **修复**: 使用 `abs(a - b) < 1e-12` 或按字符串分组。

### M2. CSV 续跑时字段名可能不匹配
- **文件**: outputs.py:30
- `DictWriter` fieldnames 由当前批次决定，非已有 header。代码版本间 dict 键顺序不同导致值写入错误列。
- **修复**: 追加模式下从已有 CSV header 读取字段名。

### M3. 硬编码 BIC 阈值在 fast_spaced_detection 中不同步
- **文件**: experiments.py:75
- **修复**: 将 `bic_delta` 作为参数传入 `fast_spaced_detection`。

### M4. 四个实验阶段代码复制粘贴
- **文件**: cli.py:229-277
- Simulation/null/resolution/extreme 四阶段相同 ~13 行结构。已有轻微漂移（null 去重键是裸 int，其他是 tuple）。
- **修复**: 提取为参数化循环。

### M5. _run_tasks 混合执行、进度和 I/O
- **文件**: cli.py:82-106
- 一个函数管 (a) 任务调度 (b) 进度打印 (c) CSV 写入。`output_path` 为 Optional 时结果静默丢弃。
- **修复**: 分离 CSV 写入到调用方。

### M6. Worker 函数在全局变量未初始化时可被调用
- **文件**: cli.py:95-98
- `workers <= 1` 时不调用 `_init_worker`。非 `main()` 上下文调用将传递 `None` 给 NumPy。
- **修复**: 添加 assert 或在单进程路径中也初始化。

---

## 🔵 低级别建议

### L1. Q1/Q2/Q3 SEED 常量分散
- Q3: `SEED = 20260620`，Q2: `SEED = 20260619`，Q1: `random_seed: int = 20260619`
- **修复**: 项目根级别统一随机种子。

### L2. GLRT 统计量/阈值与 Q1 重复
- `q1_compatible_glrt_stat` 和 `q1_compatible_glrt_threshold` 与 Q1 函数算法等价。
- **修复**: 直接导入 Q1 函数，在校正步骤做增量包装。

### L3. BIC 公式三处重复
- `n * log(max(sse/n, 1e-300)) + k * log(n)` 出现在 core.py:133, core.py:376 和 Q2 `joint_segment_fit`
- **修复**: 提取共享 `compute_bic(n, sse, k)` 函数。

### L4. pool.map 全量内存驻留
- cli.py:104 — 所有结果 dict 驻留内存直到全部完成。崩溃丢失所有。
- **修复**: 改用 `pool.imap_unordered`。

### L5. close_pair_resolver 和 music_close_pair 串行执行
- experiments.py:152-156 — 无数据依赖但串行调用。
- **修复**: worker 内线程池并行执行。

---

## 修复优先级建议

| 优先级 | 缺陷 | 理由 |
|---|---|---|
| **P0** | B1 (MUSIC tb[1]) | 所有 MUSIC 结果系统性偏倚，近频对比数据失真 |
| **P0** | B2 (golden 边界退化) | 极端工况近频可触发崩溃/错误收敛 |
| **P1** | B4 (GLRT 阈值不匹配) | 统计校准基础受损，顺序检测误报率不均 |
| **P1** | B3 (argmax 空掩码) | 虚假二源检测，窄带场景触发 |
| **P1** | B5 (Workbook 泄漏) | 数据加载崩溃，阻塞所有后续 |
| **P1** | B6/B7 (NameError) | 代码脆弱性，数据变更即崩溃 |
| **P2** | A1/A2 (双路径分离) | 仿真验证不代表真实管线 |
| **P2** | A3 (混用拟合域) | 近频接受准则内在矛盾 |
| **P2** | A4 (丢弃 lstsq 秩) | 近秩亏时优化可能错解 |
| **P3** | M1-M6 | 健壮性/可维护性 |
| **P4** | L1-L5 | 效率/代码去重 |

---

*报告由 9 角度并行审查自动合成，经去重和交叉验证后生成。Phase 3 sweep 因 API 余额不足未完成。*
