# Q4 V1 自适应传感器布局 — 第二轮代码审查

**审查日期:** 2026-06-20  
**审查范围:** `q4_adaptive_sensor_layout/` 下 10 个源文件（含 2 测试文件）  
**对比基线:** 第一轮审查 (`code_review_20260620.md`, 7 项发现)  
**关联日志:**
- `q4_v1_objective_proxy_optimization_20260620.md` — 目标函数优化（fused GLRT proxy）
- `q4_v1_robustness_validation_outputs_20260620.md` — 鲁棒性验证与 Monte Carlo 排名
- model card `q4_v1_adaptive_sensor_layout.md` — 模型注册卡

---

## 当前代码规模

| 文件 | 行数 | 变更状态 |
|------|------|----------|
| `core.py` | 454 (+66) | 目标函数重写、噪声/扰动新增、配置字段扩展 |
| `experiments.py` | 287 (+46) | validated_layouts 汇总、config 传导 |
| `outputs.py` | 216 (+22) | validated CSV 输出、报告/README 更新 |
| `run_q4_v1.py` | 98 (+19) | CLI 新增 7 个参数 |
| `tests/test_q4_v1_core.py` | 78 (**新增**) | 8 个单元测试 |
| `tests/test_q4_v1_experiments.py` | 28 (**新增**) | 1 个实验层测试 |
| `README.md` | 48 (+9) | 更新使用说明与输出结构 |

---

## 第一轮发现修复状态

| # | 第一轮发现 | 严重度 | 状态 | 证据 |
|---|-----------|--------|------|------|
| 🔴1 | prescreen <3 时 IndexError | 🔴 | ✅ **已修复** | `core.py:230-231` `raise ValueError` + `experiments.py:225-226` 判空守卫 |
| 🔴2 | one_swap 无迭代上限 | 🔴 | ✅ **已修复** | `core.py:311-330` `max_iter` + `warnings.warn` |
| 🟡3 | 目标权重硬编码 | 🟡 | ✅ **已修复** | `Q4V1Config` 新增 `weight_mean_lambda/trace_info/min_eigen/redundancy` |
| 🟡4 | 正则化 1e-12 | 🟡 | ✅ **已修复** | `cfg.eig_regularization` 默认 `1e-8` + `np.maximum(eigvals, 0.0)` |
| 🟡5 | 相似度 epsilon 门限 | 🟡 | ✅ **已修复** | `cfg.similarity_floor` 默认 `1e-12` + `max(denom, floor)` |
| 🟢6 | 零自动化测试 | 🟢 | ✅ **已修复** | 9 个 pytest 用例全通过 |
| 🟢7 | 格式转换职责重叠 | 🟢 | ⬜ 未修复 | 低优先级，不影响功能 |

**修复率: 6/7（86%）。** 唯一未修复的是低优先级代码组织问题。

---

## 第二轮新发现：5 项

### 🔴 1. 验证评分权重硬编码于 summarize_validated_layouts

- **文件:** `experiments.py:191`
- **代码:**
  ```python
  score = 0.45 * mean_pd + 0.35 * low_snr_pd + 0.20 * min_pd - 2.0 * false_alarm_excess
  ```
- **问题:** 验证评分的权重（`0.45, 0.35, 0.20, -2.0`）直接决定了哪个布局被视为"Monte Carlo 验证最优"——这与解析目标函数一样重要，但**不在 `Q4V1Config` 中、不在 CLI 参数中、不可追溯至运行时参数文件**。model card 承认 "the validation-score formula should be stated explicitly" 但这是文档承诺而非代码解决。如果论文审阅者质疑评分公式的合理性，或者需要对比不同权重下的排名稳定性，当前代码需要手动修改后重新运行。
- **对比:** 第一轮发现的 🟡3（目标权重硬编码）已被修复为可配置——验证评分公式的问题性质完全相同。
- **影响:** 论文可信度——验证排名不可复现除非运行完全相同的代码版本。如果 V1 进入论文主线，这是必须解决的。
- **修复方向:** 在 `Q4V1Config` 中增加 `validation_weight_pd: float = 0.45`、`validation_weight_low_snr: float = 0.35`、`validation_weight_min_pd: float = 0.20`、`validation_weight_fa_excess: float = -2.0`，并在 `write_runtime` 中输出。

---

### 🟡 2. 融合权重计算在 evaluate_layout 与 fused_statistics 中重复定义

- **文件:** `core.py:248-250` vs `core.py:437-439`
- **代码（evaluate_layout）:**
  ```python
  inv_var = 1.0 / np.maximum(sigma ** 2, np.finfo(float).eps)
  fusion_weights = inv_var / np.sum(inv_var)
  detection_lambdas = (DEFAULT_AMPLITUDES ** 2) * np.sum(fusion_weights[:, None] * np.abs(white) ** 2, axis=0)
  ```
- **代码（fused_statistics）:**
  ```python
  inv_var = 1.0 / np.maximum(noise_stds ** 2, np.finfo(float).eps)
  weights = inv_var / np.sum(inv_var)
  return np.sum(stats * weights[:, None], axis=0)
  ```
- **问题:** 两处独立实现了完全相同的反方差归一化逻辑。如果未来噪声加权策略改变（如引入稳健权重、不同正则化），必须同步修改两处——这正是第一轮审查中 Q4 V0 的 `write_csv` 重复问题的同类缺陷。
- **影响:** 维护风险——一处修改、另一处忘记同步导致解析目标与 Monte Carlo 检测器使用不同的融合权重，产生隐蔽的代理-检测器不对齐。
- **修复方向:** 提取 `def fusion_weight_vector(noise_stds: np.ndarray) -> np.ndarray` 到 `core.py` 模块级函数，两处调用。

---

### 🟡 3. perturb_responses 对每个 (sensor, fault) 独立扰动，而非 per-sensor 共模

- **文件:** `core.py:397-402`
- **代码:**
  ```python
  gain = np.exp(rng.normal(0.0, cfg.response_gain_jitter, responses.shape))
  phase = rng.normal(0.0, cfg.response_phase_jitter, responses.shape)
  return responses * gain * np.exp(1j * phase)
  ```
- **问题:** 物理上，一个传感器的响应不确定性来源于安装误差、校准偏差等，这些会影响**该传感器对所有频率**的响应——即同一个传感器的所有故障频率应共享同一个 gain jitter 和 phase jitter。当前实现对每个 `(sensor, fault)` 元素生成独立的随机扰动，相当于最大程度地破坏了响应结构，使鲁棒性测试比物理实际更严苛。
- **分析:** 以 `response_gain_jitter=0.15` 为例。如果 V1 选出三个传感器、四个故障频率，就有 12 个独立的 gain jitter 样本——其中最大偏差可能达到 +45%、最小偏差 -45%（2.5σ 极端值）。而 per-sensor 共模下只有 3 个 independent gain jitter 样本，极端偏差的概率大幅降低。当前实现会**系统性地高估**响应不确定性对检测率的影响。
- **影响:** 中等。鲁棒性测试结果会比真实安装场景更悲观，可能错误排除在物理世界中表现良好的布局。changelog 中的 validated best 与 analytic best 的差异（validation score 0.522 vs 0.493）部分可能源于这种过度保守的扰动模型。
- **修复方向:** 对 gain 和 phase 按传感器行做广播（`rng.normal(0.0, jitter, (len(responses), 1))`），而非按元素。同时保留 `(len(responses), len(frequencies))` 作为可选的更严苛模式，通过新的 CLI flag 控制。

---

### 🟢 4. test_generate_noise_supports_correlated_sensor_noise 使用非确定性断言

- **文件:** `tests/test_q4_v1_core.py:67-71`
- **代码:**
  ```python
  noise = generate_noise(np.asarray([1.0, 2.0, 3.0]), 2000, rng, correlation=0.5)
  corr = np.corrcoef(noise)[0, 1]
  assert corr > 0.25
  ```
- **问题:** 对于 ρ=0.5, n=2000，样本相关系数的标准误差约为 `√((1-ρ²)²/n) ≈ 0.017`。`corr > 0.25` 距离真值 0.5 约 15 个标准误差——概率上几乎不可能误触发，但严格来说是 non-deterministic。如果后续有人将 n 降到 100 或改变 seed，可能随机失败。
- **影响:** 极低——当前参数下几乎不可能 flaky。
- **修复方向:** 改为 Fisher Z 检验的确定性区间，或使用更大的安全边界（`corr > 0.40`），或添加显式确定性检查（`np.cov` 的数值特征）。

---

### 🟢 5. evaluate_layout 中旧版 lambdas 仅用于输出现已无用的字段名

- **文件:** `core.py:247, 275-278`
- **代码:**
  ```python
  lambdas = (DEFAULT_AMPLITUDES ** 2) * np.sum(np.abs(white) ** 2, axis=0)
  # ... lambdas 后续仅在 LayoutEvaluation 构造时使用:
  robust_min_lambda=robust_min,   # robust_min 来自 detection_lambdas，不是 lambdas！
  mean_lambda=float(np.mean(lambdas)),  # 旧版无权重 λ sum
  ```
- **问题:** `robust_min_lambda` 字段使用 `robust_min`（来自融合检测代理），但 `mean_lambda` 使用旧版未加权的 `lambdas`。字段命名已经语义漂移：`robust_min_lambda` 实际是融合代理的鲁棒最小值，而 `mean_lambda` 是未融合的原始 λ 均值。两者不在同一度量空间。CSV 输出中两列并排，容易让读者以为它们在同一尺度下可比较。
- **影响:** 低——不影响算法，但论文作者解读 CSV 时可能产生混淆。
- **修复方向:** 将 `mean_lambda` 重命名为 `mean_raw_lambda` 或废弃该字段（因为 `detection_mean_lambda` 已经提供融合版本）。或者统一为仅输出融合代理字段。

---

## 第二轮审查统计

| 类型 | 严重度 | 数量 | 涉及文件 |
|------|--------|------|----------|
| 可配置性缺失（验证评分） | 🔴 | 1 | `experiments.py` |
| 代码重复（融合权重） | 🟡 | 1 | `core.py` |
| 扰动模型过于保守 | 🟡 | 1 | `core.py` |
| 非确定性测试 | 🟢 | 1 | `tests/test_q4_v1_core.py` |
| 字段语义漂移 | 🟢 | 1 | `core.py` |

---

## 两轮审查累计总览

| 状态 | 数量 | 明细 |
|------|------|------|
| ✅ 已修复 | 6 | 边界守卫、迭代上限、权重可配、正则化、相似度门限、测试覆盖 |
| 🔴 新 P1 | 1 | 验证评分硬编码 |
| 🟡 新 P2 | 2 | 融合权重重复、扰动模型 |
| 🟢 新 P3 | 2 | 非确定性测试、字段语义 |
| ⬜ 遗留 P3 | 1 | 格式转换职责重叠 |

**累计严重发现:** 12 项（含已修复 6 项）。

---

## 核心算法深度验证

由于第二轮新增了 fused GLRT 代理和响应扰动，对以下关键路径进行了公式级别的逐行验证：

| 检查项 | 结论 | 备注 |
|--------|------|------|
| 融合检测代理 `detection_lambdas` (core.py:248-250) | ✅ 正确 | `Aₖ² · Σ_s(w_s · |h_sₖ|² / σ_s²)` 其中 `w_s = (1/σ_s²) / Σ(1/σ_s²)` |
| 加权对应 fused_statistics 一致 (core.py:436-439) | ✅ 一致 | 两处使用相同的逆方差归一化 |
| 等相关系数噪声生成 (core.py:387-394) | ✅ 正确 | Cholesky 式分解：`√(1-ρ)·n_ind + √ρ·σ·n_shared`，Σ[i,j] = ρ·σ_i·σ_j |
| 增益扰动对数正态 (core.py:398) | ✅ 正确 | `exp(N(0, σ²))` 保证 gain > 0，中位数 1.0 |
| 阈值保守分位数 (core.py:453) | ✅ 合理 | `method="higher"` 使阈值略高，p_fa 略有不足而非超出 |
| 校准与信号试运行使用相同 cfg.noise_correlation | ✅ 一致 | `calibrated_threshold:450` 与 `synthesize_layout_samples:424` 传递同一参数 |
| 扰动不进入校准 | ✅ 正确 | 零假设下无信号 → 无响应扰动 |
| 信号/噪声 rng 种子隔离 | ✅ 未变 | experiment_id 3000+ (信号) vs 8100+ (噪声) vs 9100+ (校准) |
| 预筛选仍使用旧得分 (core.py:187-202) | ✅ 有意 | 预筛选是粗筛，用简单 min+0.2·mean λ 避免 fusion 计算的额外开销 |

**算法正确性结论:** ✅ 无逻辑 bug。融合检测代理公式与 Monte Carlo 检测器在加权策略上一致。扰动模型有意保守。等相关系数噪声生成正确。

---

## 与 Changelog / Model Card 的交叉验证

| 文档声明 | 代码是否匹配 |
|----------|-------------|
| "Sensor responses are weighted by inverse noise variance before computing detection strength" | ✅ `core.py:248-250` fusion_weights |
| "Changed the default mean detection-strength weight to 0.10" | ✅ `Q4V1Config.weight_mean_lambda: float = 0.10` |
| "Made threshold calibration use the conservative higher quantile method" | ✅ `core.py:453` `method="higher"` |
| "Added response perturbation for signal trials" | ✅ `core.py:397-402` `perturb_responses` |
| "Added a regression test that verifies new detection proxy fields are present and positive" | ✅ `test_layout_objective_uses_fusion_detection_proxy` |
| "Added paper/q4_v1_validated_layouts.csv" | ✅ `outputs.py:207` |
| "The analytic objective best can differ from the Monte Carlo validated best under response perturbation" | ✅ 已确认——analystic 使用未扰动响应，检测试运行使用扰动响应 |
| "The current validation score is a pragmatic scalar summary, not a theorem" | ⚠️ 文档诚实但代码不可配——存在不一致 |

---

## 修复建议优先级（第二轮增量）

| 优先级 | 编号 | 问题 | 建议 |
|--------|------|------|------|
| P1 | 🔴1 | 验证评分权重硬编码 | `Q4V1Config` + CLI 暴露 4 个权重参数 |
| P2 | 🟡2 | 融合权重计算重复 | 提取 `fusion_weight_vector()` 公共函数 |
| P2 | 🟡3 | 扰动 per-element 而非 per-sensor | 改为行广播或增加 CLI flag 控制模式 |
| P3 | 🟢4 | 相关测试非确定性断言 | Fisher Z 或 `corr > 0.40` |
| P3 | 🟢5 | `mean_lambda` 字段语义漂移 | 重命名或废弃旧字段 |

---

## 总体评价（更新）

| 维度 | 第一轮 | 第二轮 | 变化 |
|------|--------|--------|------|
| 模块划分 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | — |
| 接口设计 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | config 字段完备 |
| 数值正确性 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 融合代理、扰动、相关噪声均验证正确 |
| 可配置性 | ⭐⭐⭐ | ⭐⭐⭐⭐ | 目标权重可配，验证评分仍需跟进 |
| 测试覆盖 | ⭐ | ⭐⭐⭐ | 9 个测试覆盖核心路径 |
| 文档完整性 | ⭐⭐⭐ | ⭐⭐⭐⭐ | 两份 changelog + model card + 更新 README |

**总体: A-（从 B+ 提升）。** 第一轮的 6 个 P1/P2 问题已全部修复。代码已具备进入 paper 主线的基础质量。第二轮发现的 5 个问题中，仅验证评分配置化（🔴1）值得在 official 运行前修复，其余可在后续迭代中处理。

---

*本报告由单人深度审查生成，覆盖 10 个源文件、3 份关联日志文档。代码与 changelog/model card 声明逐项交叉验证。*
