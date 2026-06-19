# Q3 Code Review 20260619

## Summary

- **总体判断**：代码质量中等偏上，核心算法逻辑（多峰GLRT顺序检测、BIC定阶、联合最小二乘）正确，无导致结果严重错误的 P0 问题。存在若干影响统计可靠性与可维护性的 P1/P2 问题，以及一批性能优化点。
- **是否建议先跑 200 次**：可以，但建议先修复 P1 问题后再跑，以保证 200 次结果的可靠性。
- **是否存在阻塞级问题**：否（无 P0）。核心数学逻辑经小规模 10 次运行已验证趋势合理。
- **建议先修复数量**：2（P1）
- **可延后修复数量**：4（P2）+ 4（P3）

---

## Findings

### P1 - 001 `estimated_full_200` 使用硬编码次数而非 CLI 参数

- **文件**：`q3_multisource_separation/cli.py`
- **行号**：226-232
- **严重度**：P1
- **类型**：正确性 / 输出一致性
- **问题**：`estimated_full_200_seconds` 的计算公式中硬编码了 `200`（仿真与近频）和 `500`（纯噪声），而非使用 `args.simulation_runs`、`args.resolution_runs`、`args.null_runs`。当用户以非默认参数运行时（如 `--simulation-runs 500`），估算值系统性偏离实际。
```
# 当前代码：
estimated_full_200 += mean_simulation_trial * len(SNR_LEVELS) * 200
estimated_full_200 += (mean_main + mean_music) * len(AMPLITUDE_CASES) * len(SEPARATIONS) * 200
estimated_full_200 += mean_null_trial * 500
```
- **影响**：
  - `q3_runtime.txt` 中输出的估算值与实际目标运行次数完全不匹配，误导用户对耗时的判断。
  - 字段名 `estimated_full_200_seconds` 与计算内容一致（都是 200），但当传入非 200 参数时，行名与实际含义产生错位。
- **复现场景**：`python run_q3.py --simulation-runs 500 --resolution-runs 500 --null-runs 1000`，输出的 `estimated_full_200_seconds` 仍按 200/500 估算，低估实际总耗时。
- **建议修复**：将硬编码的 200/500 替换为对应的 CLI 参数，同时将字段名改为 `estimated_full_seconds`（去掉 "200"）或追加实际目标次数后缀。
```python
if np.isfinite(mean_simulation_trial):
    estimated_full += mean_simulation_trial * len(SNR_LEVELS) * args.simulation_runs
if np.isfinite(mean_main_resolution) and np.isfinite(mean_music_resolution):
    estimated_full += (mean_main_resolution + mean_music_resolution) * len(AMPLITUDE_CASES) * len(SEPARATIONS) * args.resolution_runs
if np.isfinite(mean_null_trial):
    estimated_full += mean_null_trial * args.null_runs
```
- **是否阻塞 200 次测试**：是。200 次默认参数下无影响，但该问题将导致任何非默认参数的运行产生误导性输出。

---

### P1 - 002 `read_csv_rows` 每阶段全量读取 CSV，200 次后 I/O 显著放大

- **文件**：`q3_multisource_separation/cli.py`
- **行号**：146-193（三阶段重复模式）
- **严重度**：P1
- **类型**：性能
- **问题**：在 simulation、null、resolution 三个阶段各调用两次 `read_csv_rows`（阶段开始时 + 运行结束后），每次将整个 CSV 文件读入 `list[dict]`。在 200 次运行规模下：
  - `simulation_trials.csv`：5 SNR × 200 行 = 1000 行，每行约 20 字段
  - `resolution_trials.csv`：12 间隔 × 2 振幅 × 200 行 = 4800 行，每行约 30 字段
  - `null_trials.csv`：500 行
  - 合计单次全量读取约 6300 行 dict 构造，每阶段读取两次，另外每 20 行 flush 一次也会产生额外 IO
- **影响**：
  - 10 次运行时此开销可忽略（~43s 中占比极小）。
  - 200 次运行时，仅读取 CSV 累计就可能达数万行 dict 构造 × 多次读取。若结合 `--resume` 重复读取已完成的 CSV，I/O 开销叠加。
  - 读取的全部字段中，仅 `existing` 所需的 key 字段（2-3 列）被使用，其余字段被丢弃，浪费严重。
- **复现场景**：`python run_q3.py --simulation-runs 200 --resolution-runs 200`，等待三阶段各两次全量 CSV 读取。
- **建议修复**（P1 快速修复版 / P2 完整优化版）：
  1. **快速修复**：在 `cli.py` main() 中将 `simulation_rows`、`resolution_rows`、`null_rows` 作为可变列表维护，追加时就地 `extend`，避免阶段结束时重复 `read_csv_rows`。
  2. **深度优化**：实现 `read_csv_keys(path, key_columns)` 只读指定列，或将 `existing` 集合持久化到单独的 key 文件。
- **是否阻塞 200 次测试**：是。10 次运行时 ~43s 尚可，200 次时 I/O 放大可能使运行时间超出可接受范围。

---

### P2 - 003 `close_pair_resolver` 基带对称性约束过于严格

- **文件**：`q3_multisource_separation/core.py`
- **行号**：385-388
- **严重度**：P2
- **类型**：健壮性 / 边界条件
- **问题**：坐标下降法对两个基带频偏进行交替优化时，使用 `min(-1e-7, values[1] - 1e-7)` 强制左频率的搜索上限为负值，`max(1e-7, values[0] + 1e-7)` 强制右频率的搜索下限为正值。这隐含假设两个频率始终对称分布在 `center_hz`（固定为 13.5 Hz）两侧。

```python
left_hi = min(-1e-7, values[1] - 1e-7)           # 使 values[0] 无法 ≥0
right_lo = max(1e-7, values[0] + 1e-7)            # 使 values[1] 无法 ≤0
```

- **影响**：
  - 在当前测试用例（`run_resolution_trial` 中两频率始终以 13.5 Hz 对称，`seeds` 也是对称构造）下，此约束不产生错误。
  - 若将此函数复用于非对称近频场景（两频率均大于或均小于 `center_hz`），优化将无法达到全局最优甚至完全失败。
- **复现场景**：`close_pair_resolver(t, x, center_hz=13.5)`，输入信号两频率为 13.5002 Hz 和 13.5005 Hz（均大于 center_hz）。坐标下降将左频率限制在负频偏区域，永远无法收敛到 [0.0002, 0.0005] Hz 的全局最优。
- **建议修复**：移除对称性硬约束，仅保留 `values[0] < values[1]` 的排序约束：
```python
left_hi = values[1] - 1e-7                        # 仅要求左 < 右
values[0] = golden_minimize(..., -0.012, left_hi, ...)
right_lo = values[0] + 1e-7
values[1] = golden_minimize(..., right_lo, 0.012, ...)
```
- **是否阻塞 200 次测试**：否。当前测试数据均为对称分布，不影响 200 次基准结果。

---

### P2 - 004 `empirical_limit` 对后续间隔的下降敏感，可能返回 None

- **文件**：`q3_multisource_separation/experiments.py`
- **行号**：271-277
- **严重度**：P2
- **类型**：正确性 / 边界条件
- **问题**：`empirical_limit()` 要求从某个间隔 `i` 开始，**所有** 后续更大的间隔的成功率均 ≥ 0.90。若某较大间隔因抽样噪声回落到 90% 以下，函数返回 `None` 而非返回首个达到 90% 的间隔：

```python
if row[key] >= 0.90 and all(later[key] >= 0.90 for later in rows[index:]):
    return float(row["separation_hz"])
return None
```

- **影响**：
  - 当前 10 次运行数据中不存在此回落，`equal` 返回 0.005，`unequal` 返回 0.0075。
  - 200 次运行时，抽样噪声降低，回落的概率减小，但仍有可能因个别间隔的异常低值导致 `None`，需要在报告中人工处理。
  - 实际物理规律应该是近频辨识成功率随间隔增大单调非减；若出现回落应视为抽样误差，而非经验极限不存在。
- **复现场景**：`unequal` 振幅条件下，间隔 = 0.005 时 70%（抽样波动），间隔 = 0.0075/0.01 时 100%。`empirical_limit` 在 0.005 处检查 `all(later[0.0075, 0.01]) >= 0.90` 为 True，返回 0.005。但如果后期有一个异常低值（如 0.0075=100%, 0.01=80%），则 0.005 不被接受，0.0075 检索 `all([0.01]>=0.90)` 失败 → `None`。
- **建议修复**：改为向前搜索（首个到达 0.90 且后续无低于阈值的显著下降，或允许一定容差）：
```python
def empirical_limit(summary, case, method="main", threshold=0.90):
    rows = sorted(..., key=lambda r: r["separation_hz"])
    key = f"{method}_success_rate"
    for index, row in enumerate(rows):
        if row[key] >= threshold:
            remaining = [later[key] for later in rows[index:]]
            # 允许后续最多一个间隔低于阈值（排除抽样噪声）
            below = sum(r < threshold for r in remaining)
            if below <= 1:
                return float(row["separation_hz"])
    return None
```
- **是否阻塞 200 次测试**：否。200 次后抽样噪声减小，实际触发概率低，但仍需修复以保证统计稳健。

---

### P2 - 005 `experiments.py` 中 `trial_rng` 使用硬编码种子而非导入 `SEED`

- **文件**：`q3_multisource_separation/__init__.py`（第 3 行，引发不一致），`q3_multisource_separation/experiments.py`（第 31 行，问题位置）
- **严重度**：P2
- **类型**：可维护性 / 一致性
- **问题**：`__init__.py` 中定义了包级 `SEED = 20260620`，`cli.py` 中正确导入并使用 `from . import SEED`。但 `experiments.py` 中的 `trial_rng()` 直接硬编码了 `20260620`：
```python
def trial_rng(experiment_id: int, replicate: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([20260620, experiment_id, replicate]))
```
同时，`core.py` 中 `GLRTConfig` 的默认 `random_seed=20260620` 也使用硬编码。
- **影响**：
  - 若日后需要更换全局种子（如为不同实验日期重新生成独立随机序列），仅修改 `__init__.py` 的 `SEED` 不会传播到 `experiments.py` 和 `core.py` 的随机序列，导致部分随机序列不变、部分改变，破坏可复现性保证。
- **复现场景**：将 `__init__.py` 的 `SEED` 改为 20260621 后运行 `--resume`，仿真实验使用新的 `SEED`（cli.py 传递），但 `trial_rng` 仍使用旧的 20260620，前后不一致。
- **建议修复**：使 `trial_rng` 和 `GLRTConfig` 默认值从包级 `SEED` 导入：
```python
from . import SEED as PACKAGE_SEED
def trial_rng(experiment_id, replicate):
    return np.random.default_rng(np.random.SeedSequence([PACKAGE_SEED, experiment_id, replicate]))
```
- **是否阻塞 200 次测试**：否。维护性问题，不影响当前结果。

---

### P2 - 006 `_multi_sse` 在每个 golden-section 迭代中重复构建设计矩阵

- **文件**：`q3_multisource_separation/core.py`
- **行号**：148-152（`_multi_sse`），82-84（`_design_matrix`），182（调用点）
- **严重度**：P2
- **类型**：性能
- **问题**：`refine_joint_frequencies` 内部循环对每个频率的每次 golden-section 求值调用 `_multi_sse`，而 `_multi_sse` 每次都从零构造完整的 `_design_matrix`（包括所有频率的 sin/cos 列 + 截距列）。对于 k 个频率、s 次扫描、m 次 golden-section 迭代，总计 k × s × m 次重复构建设计矩阵。

以 4 频率、4 扫描、28 迭代为例：4 × 4 × 28 ≈ 448 次 `_design_matrix` 调用。每次均为 k 个频率 × 40001 采样点 × 2 列（sin + cos）= 数万次向量运算。

- **影响**：
  - 当前小规模测试中占总运行时间约 5.8s（analysis_seconds），此部分在 200 次仿真/近频实验中虽不直接叠加（仿真使用 `fast_spaced_detection`，它有类似优化问题），但 `segment_stability`（8 段 × 独立调用）中会重复触发。
  - 若后续修改频率数或采样点数，此性能问题等比放大。
- **复现场景**：`segment_stability` 调用 `refine_joint_frequencies`，每段对 4 个频率运行完整坐标下降 ≈ 448 次 lstsq，8 段 ≈ 3584 次。
- **建议修复**：将 `_multi_sse` 改为接收已构造的部分设计矩阵和待更新频率索引，仅更新被修改频率对应的 sin/cos 列；或预计算所有候选频率的列向量并通过索引查表。
- **是否阻塞 200 次测试**：否。当前 200 次仿真/近频使用 `fast_spaced_detection`（较小的优化循环），此问题主要影响 `segment_stability` 和后处理分析，不会阻塞 200 次运行。

---

### P3 - 007 `close_pair_resolver` 中坐标下降 5 轮 × golden-section 28 迭代过度收敛

- **文件**：`q3_multisource_separation/core.py`
- **行号**：376/386-388
- **严重度**：P3
- **类型**：性能 / 微优化
- **问题**：`close_pair_resolver` 中 golden-section 迭代次数为 28（坐标下降内）和 35（初始单频搜索）。28 次 golden-section 可达到括号宽度缩小因子 (0.618)²⁸ ≈ 7×10⁻⁷，初始宽度 0.024 Hz 对应终精度约 1.7×10⁻⁸ Hz，远低于物理问题所需的分辨率（FFT 频点间隔 0.0025 Hz 的万分之一）。

同样，`refine_joint_frequencies` 中 28 次 golden-section 也有类似过度收敛问题。
- **影响**：每轮坐标下降多执行约 30-50% 的 lstsq 调用。五轮坐标下降 × 2 频率 × 10 额外迭代 ≈ 100 次可避免的 lstsq 计算。
- **复现场景**：每个 `close_pair_resolver` 调用（resolution 实验中运行约 4800 次），每次可节省约 100 次 lstsq。
- **建议修复**：将核心循环迭代次数从 28 降至 18（精度 ≈ 1.7×10⁻⁵ Hz，仍优于频点间隔），初始搜索从 35 降至 22：
```python
golden_minimize(objective, lo, hi, iterations=18)  # 座标下降内
golden_minimize(objective1, -0.01, 0.01, iterations=22)  # 初始单频
```
- **是否阻塞 200 次测试**：否。纯性能优化。

---

### P3 - 008 `_match_frequencies` 排序配对在 K 不同时可能配对错误

- **文件**：`q3_multisource_separation/experiments.py`
- **行号**：38-42
- **严重度**：P3
- **类型**：正确性（当前无影响）
- **问题**：`_match_frequencies` 将估计频率和真实频率各自排序后按索引配对。当长度不等时，`count = min(len(estimated), len(truth))` 截取前 count 个。排序配对的假设是「最小的估计 ↔ 最小的真实」，这在频率分布不均匀时可能产生错误配对。

```python
# 示例：truth=[4.0, 14.0], estimated=[14.0]
# 排序后 truth=[4.0, 14.0], est=[14.0]
# count=1, 配对 (14.0, 4.0) → MAE=10.0 Hz
# 正确配对应为 (14.0, 14.0) → MAE=0.0 Hz
```
- **影响**：
  - 当前代码中，当 K 不同时（`correct_k=False`），`frequency_mae` 在 `run_simulation_trial` 第 99 行被覆盖为 NaN。因此 `_match_frequencies` 的排序配对问题仅在 `correct_k=True` 时影响 MAE。
  - 当 `correct_k=True` 时，两数组长度相同，排序后按索引配对天然正确（假设频率值一一对应且相近，排序后索引自然配对相近频率）。
  - 因此当前代码中没有实际的错误影响，但函数本身脆弱，未来若在其他场景使用需注意。
- **复现场景**：在 `correct_k=False` 且未覆盖为 NaN 的场景下（若未来修改代码），产生错误的频率误差统计。
- **建议修复**：实现基于最小距离的分配（匈牙利算法的一维特化）：
```python
def _match_frequencies(estimated, truth):
    from scipy.optimize import linear_sum_assignment  # 或手动实现贪心最近邻
```
或至少添加函数注释说明配对约束。
- **是否阻塞 200 次测试**：否。

---

### P3 - 009 `_complex_fit` 与 `multi_harmonic_fit` 结构重复

- **文件**：`q3_multisource_separation/core.py`
- **行号**：104-145（`multi_harmonic_fit`），350-362（`_complex_fit`）
- **严重度**：P3
- **类型**：可维护性
- **问题**：两函数实现几乎相同的流程：排序频率 → 构建设计矩阵 → lstsq → 计算残差/SSE/BIC → 调用 `design_diagnostics`。`parameter_count` 的推导在两处独立书写（`3k+1` vs `3k+2`），BIC 公式完全一致但需要手动同步。
- **影响**：若未来修正 BIC 公式、参数计数规则或添加新的诊断指标，须同时修改两处。当前两处已存在细微差异（`multi_harmonic_fit` 额外计算 per-component 的 waveform、振幅、相位），增加了阅读成本。
- **复现场景**：任何对 BIC 公式或设计矩阵结构的修改，开发者可能遗漏两处中的一处。
- **建议修复**：抽象出共享的拟合框架 `_generic_fit(t, columns_builder, parameter_count_fn)`，或至少添加注释标注两函数需同步修改的字段。
- **是否阻塞 200 次测试**：否。

---

### P3 - 010 `when correct_k=False` 时 `frequency_mae` 被覆盖为 NaN

- **文件**：`q3_multisource_separation/experiments.py`
- **行号**：99
- **严重度**：P3
- **类型**：信息损失 / 设计取舍
- **问题**：第 91 行已计算 `frequency_mae = float(np.mean(np.abs(ef - tf)))` 且信息有效（例如估计对了 3 个中的 2 个频率，平均误差很小）。但第 99 行无条件覆盖为 NaN。虽然有意识的设计决策（限 K 正确时评价频率精度），但丢失了部分正确的信息。
- **影响**：`summarize_simulation` 中 `mean_frequency_mae_hz_given_correct_k` 在 K 不完全正确时无样本，导致总体报告中的频率误差样本量小于正确 K 样本量，可能低估高频段性能。
- **复现场景**：-15 dB 时 `correct_k_rate=0.8`（10 次中 8 次正确），2 次不正确 → 频率 MAE 仅 8 个样本。若 K=5 真实、估计=4 但误差极小，这些信息被丢弃。
- **建议修复**（可选）：增加 `frequency_mae_all` 字段（不限 K 正确性），或至少添加注释说明这一设计取舍。
- **是否阻塞 200 次测试**：否。设计取舍而非错误。

---

## Suggested Order

### 1. 必须先修（200 次前）

| 优先级 | ID | 标题 |
|--------|----|------|
| P1-001 | `estimated_full_200` 使用硬编码次数 | 虽不影响结果正确性，但 200 次输出的 runtime 估算严重失准时会误导后续优化决策 |
| P1-002 | `read_csv_rows` 全量读取 CSV | 200 次规模下 I/O 放大效应显著，可能使运行时间不可控 |

### 2. 可在 200 次后修

| 优先级 | ID | 标题 | 原因 |
|--------|----|------|------|
| P2-003 | `close_pair_resolver` 对称约束 | 当前测试数据对称分布，不影响结果 |
| P2-004 | `empirical_limit` 回落敏感性 | 仅在小样本或极端抽样波动时触发 |
| P2-005 | 种子硬编码 | 维护性问题，不影响当前结果 |
| P2-006 | `_multi_sse` 重复构建设计矩阵 | 性能优化，200 次运行前可暂缓 |

### 3. 只记录不修

| 优先级 | ID | 标题 | 原因 |
|--------|----|------|------|
| P3-007 | golden-section 过度收敛 | 纯性能微优化，200 次不影响 |
| P3-008 | `_match_frequencies` 排序配对 | 当前无实际影响 |
| P3-009 | `_complex_fit` / `multi_harmonic_fit` 重复 | 可维护性，当前无风险 |
| P3-010 | `correct_k=False` 时 MAE NaN | 设计取舍，非错误 |

---

## Runtime Notes

- **当前耗时输出是否够用**：基本够用。`q3_runtime.txt` 提供了按阶段的细分（load/analysis/simulation/null/resolution/output）和均值指标。但缺少以下维度：
  - 三阶段各自的 flush 等待时间（CSV 写入 I/O）未单独计时
  - `fast_spaced_detection` 内部单次迭代耗时未统计
  - 图片转换（Chrome headless PNG 渲染）未单独计时，包含在 `output_stage_seconds` 内
- **是否建议增加 `q3_timing.csv`**：建议增加。结构化 CSV（`stage`, `step`, `seconds`, `n_calls`, `description`）将使后续的耗时变化追踪和性能回归检测变得可自动化，而非依赖 `q3_runtime.txt` 的自由文本。可以在 `P1-002` 修复的同时实现。
- **预计主要瓶颈**：
  - 200 次规模下：多源仿真（5 SNR × 200 次 = 1000 次 `fast_spaced_detection`）将是最大耗时阶段，每次 ~400 ms，合计 ~400 s。
  - 近频实验（2 振幅 × 12 间隔 × 200 次 = 4800 次，每次主模型 + MUSIC ≈ 48 ms）合计 ~230 s。
  - CSV 全量读取 I/O（P1-002）将额外叠加数十秒至分钟级开销。
- **CPU 多进程是否值得**：值得。仿真和近频实验是天然"易并行"（embarrassingly parallel）负载，各 replicate 间完全独立。使用 `concurrent.futures.ProcessPoolExecutor` 可在 4-8 核机器上实现 3-6 倍加速。需要注意：
  - Windows 多进程需在 `__main__` 保护下使用 `spawn` 启动方式
  - 每 20 次 flush 的 CSV 写入需用锁保护或改为阶段结束时统一写入
  - 当前基于 dict 的 `--resume` 机制需要支持并发写入（如每个 replica 写入独立文件，最后合并）
- **CUDA 是否值得**：不值得。当前向量长度（40001 点，设计矩阵 9-15 列）和问题规模（每个 replicate 独立 500 次小矩阵 lstsq + FFT）对 GPU 计算来说太小。数据搬运开销超过计算加速收益。若未来扩展为大规模批处理（10⁴+ 独立的 Monte Carlo replica），或单次 FFT 长度增加到 10⁶+ 点，可重新评估。
