# Q4 传感器布局代码审查报告

**审查日期:** 2026-06-20  
**审查范围:** `q4_sensor_layout/` 下 6 个 Python 源文件  
**审查方法:** 7 维度 × 4 视角分片并行审查 + 1-vote 逐项验证  
**审查参与:** 逐行正确性扫描、跨文件数据流追踪、复用/简化/效率扫描、架构深度审查

| 文件 | 行数 | 功能 |
|------|------|------|
| `core.py` | 283 | 数值核心：信号合成、检测统计量、阈值校准、评分 |
| `experiments.py` | 181 | MC 实验编排、结果汇总与布局排名 |
| `outputs.py` | 227 | CSV / PNG / Markdown 输出 |
| `run_q4.py` | 76 | 单次实验 CLI 入口 |
| `run_q4_overnight.py` | 136 | 夜间批量实验启动器 |
| `summarize_overnight.py` | 97 | 夜间实验结果汇总 |

---

## 审查结果：8 项发现

### 🔴 1. 报告评分公式硬编码（CONFIRMED）

- **文件:** `outputs.py:131`
- **问题:** Markdown 报告中的评分公式被硬编码为：
  ```
  J(S) = P̅_D - 2P_FA - 0.5 Var
  ```
  但实际评分函数 `score_layout()`（`core.py:282`）从 `Q4Config` 读取 `lambda_pfa` 和 `mu_balance`。夜间作业 `score_sensitivity_seed20260624` 使用 `--lambda-pfa 3.5 --mu-balance 1.2`，但生成的报告仍显示 `2` 和 `0.5`。没有任何代码路径从 `cfg` 动态读取这些参数生成公式。
- **修复方向:** 将 `{cfg.lambda_pfa}` 和 `{cfg.mu_balance}` 通过 f-string 嵌入公式字符串。

---

### 🔴 2. 覆盖数据跨场景混合且无场景标签（PLAUSIBLE）

- **文件:** `experiments.py:86-98`
- **问题:** `summarize_rows()` 接收所有 4 个场景的 detection rows 混合在一起，按 `(layout, snr_db)` 分组时**不按场景过滤**。输出的 `q4_fault_coverage.csv` 不含 `scenario` 列，读者无法区分是哪个场景的检测率。虽然 `robustness_rows` 部分做了逐场景分析（`experiments.py:150-163`），但主输出未提示这是跨场景平均。
- **影响:** 不了解设计的人会误以为覆盖数据是单一场景下的检测率。
- **修复方向:** 在 coverage_rows 输出中加入 `scenario` 列，或改为在 `summarize_rows` 的 `grouped` 字典中加入 scenario 维度。

---

### 🔴 3. 空数据 / 缺传感器数时崩溃（PLAUSIBLE）

- **文件:** `outputs.py:107-109`
- **代码:**
  ```python
  best = ranking[0]                                    # IndexError if empty
  best_three = next(row for row in ranking if row["sensor_count"] == 3)  # StopIteration
  best_single = next(row for row in ranking if row["sensor_count"] == 1) # StopIteration
  ```
- **问题:** 当 `runs=0` 或 `false_alarm_runs=0`（用户传参）时 ranking 为空 → `IndexError`。若未来 `all_layouts()` 的 `max_sensors` 改为 1 或 2，`sensor_count==3` 的行不存在 → `StopIteration`。
- **影响:** 边界条件下的功能完全崩溃。
- **修复方向:** `ranking[0]` 前判空，`next()` 加 `default=None` 兜底。

---

### 🟡 4. coverage_rows 对全列表反复扫描（CONFIRMED）

- **文件:** `experiments.py:86-89, 151-153`
- **问题:** `coverage_rows` 为每个 SNR 值重新对 `detection_rows` 做列表推导过滤（O(N) × 6 次 ≈ 157 万次冗余迭代），但已构建好的 `grouped` 字典只需 O(1) 查找。Robustness 循环也重新过滤全部行 × 4 次场景并再次调用 `summarize_rows`。每次运行总计浪费约 **700-800 万次冗余列表迭代**。
- **计算:**
  - 主调用：4 场景 × 42 布局 × 6 SNR × 260 runs = 262,080 行
  - coverage_rows 重扫描：262,080 × 6 SNR = 1,572,480 次
  - 4 次 robustness 调用各重复上述扫描：1,572,480 × 4 = 6,289,920 次
- **修复方向:** `coverage_rows` 改用 `grouped` 字典查找；robustness 部分在数据生成阶段即按场景分流。

---

### 🟡 5. write_csv 函数在模块间重复（CONFIRMED）

- **文件:** `outputs.py:23` / `summarize_overnight.py:17`
- **问题:** 两个模块各自实现了一个完全相同的 `write_csv()`：
  ```python
  def write_csv(path: Path, rows: list[dict]) -> None:
      if not rows: return
      path.parent.mkdir(parents=True, exist_ok=True)
      with path.open("w", newline="", encoding="utf-8-sig") as handle:
          writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
          writer.writeheader()
          writer.writerows(rows)
  ```
- **影响:** 任何 CSV 输出格式变更必须同步修改两处，存在发散风险。
- **修复方向:** 提取到共享模块（如 `_io.py`）。

---

### 🟡 6. basis_matrices 在 replicate 内层循环重复计算（CONFIRMED）

- **文件:** `experiments.py:138-139` / `core.py:228-229`
- **问题:** `evaluate_detection_trial()` 每次调用都重新计算 `default_time_axis()` 和 `basis_matrices()`（分配 arange + 计算 4×4000 点的 sin/cos），但 `t` 和 `frequencies` 在一次实验运行中固定不变。在 4 场景 × 42 布局 × 6 SNR × 200 run ≈ **20 万次**调用中每次结果相同。
- **影响:** 约 20 万次冗余的 numpy 数组分配和三角函数计算。
- **修复方向:** 将 `t`、`sin_basis`、`cos_basis` 提升到 `run_experiments` 的外层循环中，一次性预计算后传入。

---

### 🟡 7. fused_statistics 重复构建 layout_indexes 字典（CONFIRMED）

- **文件:** `core.py:137, 194-196`
- **问题:** `layout_indexes()` 每次从 `SENSOR_NAMES` 动态构建 `{name: index}` 字典（约 30 万次调用 × 6 个传感器），但 `SENSOR_NAMES` 是模块级常量。
- **影响:** 约 30 万次不必要字典推导和传感器名列表遍历。
- **修复方向:** 将 `{name: index}` 字典构建为模块级常量，`layout_indexes` 改为单次元组构造。

---

### 🟢 8. score_layout 的 lambda_pfa 项区分度有限（PLAUSIBLE）

- **文件:** `core.py:280-282`
- **问题:** `score_layout` 中 `mean_pd - lambda_pfa * p_fa - mu_balance * balance_var` 的 `p_fa` 项与阈值校准功能重叠：`calibrated_threshold` 已通过 MC 确保各布局的虚警率 ≈ `cfg.p_fa`（约 0.05）。各布局间 `p_fa` 差异主要来自 MC 估计噪声而非真实虚警差异。
- **影响:** 参数 `--lambda-pfa` 看起来能控制检测-虚警权衡，实际上对排序影响很小。
- **修复方向:** 无紧急修复必要——该参数作为安全性网仍有微弱价值，但建议在文档中说明其实际作用。

---

## 总结

| 类型 | 严重程度 | 数量 | 涉及文件 |
|------|----------|------|----------|
| 文档-代码不一致 | 🔴 | 1 | `outputs.py` |
| 边界崩溃 | 🔴 | 1 | `outputs.py` |
| 数据解释性缺陷 | 🔴 | 1 | `experiments.py` |
| 冗余计算-性能 | 🟡 | 3 | `experiments.py`, `core.py` |
| 代码复用-可维护性 | 🟡 | 1 | `outputs.py`, `summarize_overnight.py` |
| 设计权衡 | 🟢 | 1 | `core.py` |

**核心算法正确性:** ✅ 验证通过。统计量归一化、阈值校准（`chi²₂` 分布）、随机数种子（三个公式的 experiment_id 范围无重叠）均正确。

**主要改进方向:** 报告与运行参数对齐、大数据量下的扫描效率、边界鲁棒性、代码复用。

---

*本报告由 7 维度 × 4 视角并行审查生成，结果经独立验证 agent 逐项裁决。*
