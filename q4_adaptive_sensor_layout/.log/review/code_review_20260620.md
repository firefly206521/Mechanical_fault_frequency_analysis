# Q4 V1 自适应传感器布局 代码审查报告

**审查日期:** 2026-06-20  
**审查范围:** `q4_adaptive_sensor_layout/` 下 7 个 Python 源文件  
**审查方法:** 逐文件深度阅读 → 架构/算法/数值/质量四维度评估  
**审查参与:** 单 reviewer（非并行多 agent）

| 文件 | 行数 | 功能 |
|------|------|------|
| `__init__.py` | 3 | 包声明 + SEED 常量 |
| `core.py` | 388 | 数值核心：候选点生成、信号合成、布点评分、贪心/swap/全枚举搜索、GLRT 阈值校准 |
| `experiments.py` | 241 | 实验编排：profile 预设、试运行循环、检测率汇总 |
| `outputs.py` | 194 | 输出生成：CSV、中文报告、PNG 曲线图/热力图 |
| `_io.py` | 19 | 共享 CSV writer |
| `run_q4_v1.py` | 79 | CLI 入口：参数解析 → 实验运行 → 输出写入 |
| `README.md` | 39 | 使用说明 |

---

## 审查结果：7 项发现

### 🔴 1. 预筛选返回 <3 候选时 exhaustive_layouts 直接 IndexError

- **文件:** `experiments.py:191`
- **代码:**
  ```python
  exhaustive = exhaustive_layouts(points, candidate_indexes, max(top_layouts, 10))
  best = exhaustive[0]  # IndexError if exhaustive is empty
  ```
- **问题:** `prescreen_points()` 有兜底逻辑确保 `len(selected) >= min(3, len(installable))`，但如果所有候选点都是非可安装（`installable=False`），`installable` 列表为空，`selected` 保持空列表，兜底也无效。虽然当前网格参数下 `(index % 17) != 0` 保证绝大部分可安装，但这是**无防护的崩溃路径**。只要有人改了 `generate_candidate_points` 的 `installable` 判定逻辑，就可能触发。
- **影响:** 边界输入下程序静默崩溃，无任何错误信息。
- **修复方向:**
  1. `prescreen_points` 返回前检查 `len(selected) < 3` 并 `raise ValueError`
  2. `experiments.py` 中 `exhaustive_layouts` 调用后判空再取 `best`

---

### 🔴 2. one_swap_search 无迭代上限，可能无限循环

- **文件:** `core.py:270-288`
- **代码:**
  ```python
  while improved:
      improved = False
      ...
      if trial.objective > best.objective + 1e-12:
          best = trial
          improved = True
  ```
- **问题:** 没有 `max_iter` 守卫。在数值平局（两个布局的 objective 在浮点精度内交替改进）或目标函数出现循环提升路径时，`while` 可能执行大量轮次甚至无限循环。当前规模下（prescreen ≤ 40 点，3 选 3）未触发，但这是**缺少防御性编程**的典型问题。
- **影响:** 病态输入下 CPU 空转，无法终止。
- **修复方向:** 增加 `max_iter = len(candidate_indexes) * len(initial.layout)` 上限，超出时 `warnings.warn` 并退出。

---

### 🟡 3. 目标函数权重硬编码且无文档

- **文件:** `core.py:242`
- **代码:**
  ```python
  objective = (robust_min
               + 0.08 * mean_lambda
               + 0.002 * math.log1p(max(trace_info, 0.0))
               + 0.002 * min_eig
               - 0.03 * redundancy)
  ```
- **问题:** 权重 `0.08`、`0.002`、`0.002`、`0.03` 直接决定了哪个布局"最优"，但：
  - `Q4V1Config` 中没有对应字段，无法通过 CLI 调整
  - 代码中没有注释解释这些权重的含义或来源
  - `trace_info` 被计算但在 `LayoutEvaluation` 中**未存储**，无法追溯这个分量对最终排序的贡献
  - 没有 sensitivity analysis 文档说明权重变化对布局排序的影响
- **影响:** 任何人对目标函数做调整必须改源码重新运行；论文审阅者无法判断权重选择的合理性。
- **修复方向:**
  1. 在 `Q4V1Config` 中暴露 `objective_weights = (1.0, 0.08, 0.002, 0.002, -0.03)` 或类似字段
  2. 在 `LayoutEvaluation` 中增加 `trace_info` 字段
  3. 在报告或 README 中注明权重含义

---

### 🟡 4. evaluate_layout 信息矩阵正则化过于微小

- **文件:** `core.py:231`
- **代码:**
  ```python
  eigvals = np.linalg.eigvalsh(info.real + 1e-12 * np.eye(info.shape[0]))
  ```
- **问题:** 对于 3 传感器布局，`info`（4×4，秩 ≤3）有一个理论上为零的特征值。正则化 `1e-12` 极其微小，`eigvalsh` 可能返回接近零甚至略负的值（在 double precision 数值误差范围内）。虽然对 `min_eig` 的影响在目标函数中微乎其微（`0.002 * (-1e-13)`），但不够干净。
- **影响:** 极小——仅影响 `min_eigen_info` 字段和 `objective` 中占比 0.2% 的项。但若后续有人复用 `logdet_info`（`slogdet` 也加了 `1e-6` 正则化）或 `min_eigen_info` 做统计推断，可能产生误解。
- **修复方向:** 正则化统一为 `1e-8` 并对 `eigvals` 做 `np.maximum(eigvals, 0)` 后再取最小。

---

### 🟡 5. 响应相似度在弱信号点之间偏高

- **文件:** `core.py:192-196`
- **代码:**
  ```python
  def response_similarity(a: np.ndarray, b: np.ndarray) -> float:
      denom = float(np.vdot(a, a).real * np.vdot(b, b).real)
      if denom <= np.finfo(float).eps:
          return 1.0
      return float(abs(np.vdot(a, b)) ** 2 / denom)
  ```
- **问题:** 当两个点的白化响应模长都极小时（噪声主导），`denom ≤ eps` 触发 → 返回 1.0（完全冗余）。这会导致预筛选阶段将原本不应冗余的低响应点标记为冗余，可能被错误排除。当前阈值 `eps ≈ 2.2e-16` 意味着只有当 `|a|·|b| < 4.7e-8` 时才触发——这在信号存在时不太可能，但在远距离低响应候选点上不是不可能。
- **影响:** 低——白化响应模长通常在 0.001 以上（归一化后），`denom` 远大于 `eps`。防御性代码本身正确但门限偏保守。
- **修复方向:** 将门限提升到 `1e-12` 或直接使用 `max(denom, 1e-12)` 而非早退返回 1.0。

---

### 🟢 6. 缺少任何形式的自动化测试

- **文件:** 整个包
- **问题:** 项目包含数值优化（贪心搜索、swap 局部搜索）、统计推断（GLRT 阈值 Monte Carlo 校准）、数据变换流水线，但除了 `run_q4_v1.py --profile smoke` 作为手动冒烟测试外，**没有任何 `test_*.py` 单元测试或集成测试**。changelog 中提到 `python -m compileall` 作为"验证"——但这只检查语法，不检查逻辑。
- **影响:** 重构或参数调整后无法快速确认正确性；回归风险完全依赖开发者手动重跑。
- **修复方向:** 至少添加以下测试：
  1. `test_core.py::test_generate_candidate_points_returns_correct_count` — 验证输出点数和点 ID 格式
  2. `test_core.py::test_prescreen_respects_limits` — 验证预筛选数量在 `[prescreen_min, prescreen_max]` 内
  3. `test_core.py::test_greedy_layout_monotonic` — 验证逐步加传感器时 objective 不降（或不降）
  4. `test_core.py::test_exhaustive_finds_best_or_equal_to_greedy` — 验证全枚举最优 ≥ 贪心最优
  5. `test_core.py::test_calibrated_threshold_cached` — 验证 LRU 缓存生效

---

### 🟢 7. _candidate_rows / _layout_rows 与 outputs.py 职责重叠

- **文件:** `experiments.py:54-94` vs `outputs.py`
- **问题:** `_candidate_rows()` 和 `_layout_rows()` 将领域对象展平为字典列表，这个职责更适合 `outputs.py`（输出格式化层）。目前散落在 `experiments.py` 中，而 `outputs.py` 又在绘图时重新解析这些字典（如 `context["selected_layout_rows"][0]["layout"].split("+")`）。两处都在做格式转换，但没有统一的转换层。
- **影响:** 低——当前代码仍可维护，但后续添加新的输出格式时需要理解两处的转换约定。
- **修复方向:** 将 `_candidate_rows` 和 `_layout_rows` 移到 `outputs.py`（或新建 `_formats.py`），`experiments.py` 只返回领域对象。

---

## 统计汇总

| 类型 | 严重程度 | 数量 | 涉及文件 |
|------|----------|------|----------|
| 边界崩溃 | 🔴 | 2 | `core.py`, `experiments.py` |
| 可配置性/文档缺失 | 🟡 | 1 | `core.py` |
| 数值精度/鲁棒性 | 🟡 | 2 | `core.py` |
| 测试覆盖缺位 | 🟢 | 1 | 全包 |
| 代码组织 | 🟢 | 1 | `experiments.py`, `outputs.py` |

---

## 核心算法正确性

✅ **验证通过。** 对以下算法路径逐行确认：

| 检查项 | 结论 |
|--------|------|
| 信号合成模型（`_response_at`） | ✅ 方向性 + 模态 + 衰减 + 相位，物理启发，参数有意简化 |
| 白化非中心参数 λₖ(S) | ✅ 正确实现 `Aₖ² · |hₖ/σ|²` |
| 预筛选冗余门控 | ✅ 响应相似度余弦平方，门限 0.97 合理 |
| 贪心 + one-swap 搜索 | ✅ 贪心选最大增量，swap 搜索所有邻域 |
| 全枚举最优性验证 | ✅ `itertools.combinations` 覆盖所有 C(N,3) 组合 |
| GLRT 阈值 Monte Carlo 校准 | ✅ 噪声-only 重复采样 → 1-p_fa 分位数，独立 rng |
| 检测统计量投影 | ✅ 正弦/余弦投影 → χ²-like 统计量，与 Q4 V0 一致 |
| 随机数种子隔离 | ✅ `trial_rng` 使用 `(seed, experiment_id, replicate)` 三级种子，信号/噪声/校准互不重叠 |

---

## 架构评价

| 维度 | 评分 | 备注 |
|------|------|------|
| 模块划分 | ⭐⭐⭐⭐⭐ | core / experiments / outputs / cli 四层清晰 |
| 接口设计 | ⭐⭐⭐⭐ | dataclass 不可变、函数签名明确、无全局状态 |
| 数值正确性 | ⭐⭐⭐⭐ | 无逻辑 bug，细节（正则化、除零守卫）基本到位 |
| 可配置性 | ⭐⭐⭐ | profile 机制好，但目标函数权重不可配 |
| 测试覆盖 | ⭐ | 零自动化测试 |
| 文档完整性 | ⭐⭐⭐ | README 覆盖使用，报告覆盖结论，缺少设计文档 |

**总体: B+（良好，可交付但建议修复 P1 项后进入 official）**

---

## 修复建议优先级

| 优先级 | 编号 | 问题 | 建议 |
|--------|------|------|------|
| P1 | 🔴1 | prescreen <3 时 IndexError | `exhaustive_layouts` 调用后判空；`prescreen_points` 返回前 raise |
| P1 | 🔴2 | one_swap 无迭代上限 | 加 `max_iter` + `warnings.warn` |
| P2 | 🟡3 | 目标权重硬编码 | `Q4V1Config` 暴露权重；`LayoutEvaluation` 增加 `trace_info` |
| P2 | 🟡4 | 信息矩阵正则化 1e-12 | 统一到 `1e-8` + `np.maximum(eigvals, 0)` |
| P3 | 🟡5 | 相似度 epsilon 门限 | 改为 `max(denom, 1e-12)` |
| P3 | 🟢6 | 无自动化测试 | 添加 smoke 级 5 个单元测试 |
| P3 | 🟢7 | 格式转换职责重叠 | 移到 `outputs.py` 或新建 `_formats.py` |

---

*本报告由单人深度阅读生成，覆盖 7 个源文件共 ~960 SLOC。*
