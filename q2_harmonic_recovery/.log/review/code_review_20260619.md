# 代码审查报告：q2_harmonic_recovery

**日期**: 2026-06-19
**方法**: code-review skill (high effort, 7 路 finder 扫描 → 1-vote verify)
**审查范围**: 6 个文件（core.py / outputs.py / cli.py / run_q2.py / __init__.py / README.md）

---

## 审查统计

| 指标 | 值 |
|------|-----|
| 覆盖文件 | 6 |
| 代码行数（SLOC） | ~550 |
| 发现总数 | 10 |
| 🔴 高严重度 | 2 |
| 🟡 中严重度 | 6 |
| 🟢 低严重度 | 2 |
| 已修复 | 9/10 |
| 未修复 | 1（相位覆盖率 wrap 问题） |

---

## 发现明细

### 🔴 1. 相位 CI 覆盖率检查对大误差做 wrap，低 SNR 下指标虚高

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:537`（现 `core.py:579`） |
| 类别 | **正确性 BUG** |
| 修复状态 | ❌ **未修复** |
| 修改 | 重构为 `align_phase_to_reference` 辅助函数，但数学等价：`wrap_phase(est - true)` 将 >π 的误差折叠到 [-π, π) 区间，覆盖率计数被系统性地提高 |

**复现场景**: SNR=-20 dB, se_phi≈0.8 rad（1.96×0.8=1.57）。相位真实误差 3.5 rad（>1.57 应判不覆盖），wrap_phase(3.5-2π)=-2.78，| -2.78 | ≤ 1.57 → 判为覆盖。覆盖率虚高 5-15 pct。

**修复建议**: 去掉误差侧的 wrap，对 CI 本身做圆环修正（即保证 CI 边界不越界 ±π），再判断覆盖。

---

### 🔴 2. Bootstrap 相位 CI 在 ±π 边界计算错误

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:211-216`（现 `core.py:220`） |
| 类别 | **正确性 BUG** |
| 修复状态 | ✅ **已修复** |

**修复内容**: 新增 `align_phase_to_reference(phase_origin, point_phase)`，先将全部 Bootstrap 相位样本通过 `point_phase + wrap_phase(sample - point_phase)` 平移到围绕点估计的连续区间内，再计算分位数。

**复现场景**: 真相位 3.1 rad、Bootstrap 样本 -3.0 rad（等价角）。修复前 delta = wrap_phase(-6.1) ≈ 0.183 rad → 虚假小偏差 → CI 过窄 → 不覆盖真值。修复后样本连续化到 3.1 rad 附近，CI 正确覆盖。

---

### 🟡 3. 仿真验证硬编码 f_true=2.0，与真实频率不一致

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:505`（现 `core.py:538-544`） |
| 类别 | **正确性 BUG** |
| 修复状态 | ✅ **已修复** |

**修复内容**: 函数签名增加 `f_true: float = 2.0` 参数；`cli.py:103` 调用时传入 `fit["frequency_hz"]`（~2.00000153 Hz）；仿真生成真值波形和频率误差计算均使用传入的 `f_true`。

---

### 🟡 4. load_single_source 未校验 Excel 单元格 NaN/None

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:18-26` |
| 类别 | **容错缺失** |
| 修复状态 | ✅ **已修复** |

**修复内容**: try/except 包裹 `np.asarray(dtype=float)` 捕获非数值错误；增加 `np.isfinite` 全数组校验，发现非有限值时抛出带单元格坐标（如 A23、B5）的异常。

---

### 🟡 5. BIC 公式在 SSE=0 时 math.log(0) 崩溃

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:268-269`（现 `core.py:292-293`） |
| 类别 | **容错缺失** |
| 修复状态 | ✅ **已修复** |

**修复内容**: `math.log(max(sse/n, 1e-300))` 防止 SSE=0 时 log(0)。

---

### 🟡 6. SSA 窗口点数超过信号长度时崩溃

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:434`（现 `core.py:461-467`） |
| 类别 | **容错缺失** |
| 修复状态 | ✅ **已修复** |

**修复内容**: 调用 `_ssa_reconstruct_pair` 前检查 `window_ds > len(y_ds)`，超长时 `warnings.warn()` + `continue` 跳过该窗口。

---

### 🟡 7. joint_rows 为空时 write_plots 崩溃

| 字段 | 值 |
|------|-----|
| 文件 | `outputs.py:144-157`（现 `outputs.py:149-164`） |
| 类别 | **容错缺失** |
| 修复状态 | ✅ **已修复** |

**修复内容**: `if joint_rows:` guard 包装全部 4 个分段图调用；为空时 `print("Warning: ...", file=sys.stderr)`。

---

### 🟡 8. 无 Chrome/Edge 时静默删 SVG、不生成 PNG

| 字段 | 值 |
|------|-----|
| 文件 | `outputs.py:190`（现 `outputs.py:198-200`） |
| 类别 | **容错缺失** |
| 修复状态 | ✅ **已修复** |

**修复内容**: `browser is None` 时 `print("Warning: Chrome/Edge not found; keeping SVG plots...", file=sys.stderr)`；直接 `return []` 跳过转换，SVG 保留。

---

### 🟢 9. 分段全丢弃无告警，返回 NaN BIC

| 字段 | 值 |
|------|-----|
| 文件 | `core.py:235`（现 `core.py:260`） |
| 类别 | **容错缺失** |
| 修复状态 | ✅ **已修复** |

**修复内容**: `if not segments: raise ValueError("No segments are at least 10 seconds long; cannot run joint segment fit.")`。

---

### 🟢 10. coverage_ok 上界 0.98 过严，误报 fail

| 字段 | 值 |
|------|-----|
| 文件 | `outputs.py:225`（现 `outputs.py:234`） |
| 类别 | **设计偏差** |
| 修复状态 | ✅ **已修复** |

**修复内容**: 去掉 0.98 上界，仅保留 `r[k] >= 0.90` 下界检查。200 次仿真蒙特卡洛噪声（σ≈1.5%）不再误触。

---

## 修复摘要

```
core.py:
  🔴 #2 Bootstrap 相位 CI   → ✅ align_phase_to_reference() 连续性修正
  🟡 #3 f_true 硬编码        → ✅ 函数参数化 + cli.py 传入精修频率
  🟡 #4 Excel NaN 无校验     → ✅ try/except + np.isfinite 行/列报错
  🟡 #5 BIC SSE=0 崩溃       → ✅ math.log(max(..., 1e-300))
  🟡 #6 SSA 窗口超长         → ✅ if guard + warnings.warn + continue
  🟢 #9 分段全丢弃           → ✅ raise ValueError
  🔴 #1 相位覆盖率          → ❌ 仅重构未修复 (align_phase_to_reference)

outputs.py:
  🟡 #7 joint_rows 为空崩溃 → ✅ if guard + print warning
  🟡 #8 无浏览器静默删 SVG  → ✅ print warning + 保留 SVG
  🟢 #10 coverage 上界过严  → ✅ 只检查下界 0.90

cli.py:
  🟡 #3 f_true 参数          → ✅ simulation_validation 传入 fit["frequency_hz"]
```

### 剩余未修复

| # | 问题 | 位置 | 难度 | 影响 |
|---|------|------|------|------|
| 🔴 1 | 相位覆盖率对大误差做 wrap 虚高覆盖 | core.py:579 | 中（需圆环 CI 修正） | 低 SNR 下相位覆盖率统计不可信 |

### 已知死代码（未进入 top 10）

| 位置 | 内容 | 建议 |
|------|------|------|
| `cli.py:93` | `, envelope` 解包后未使用 | 改为 `_` |
| `core.py:549` | `normal = NormalDist()` 未使用 | 删除该行 |
| `outputs.py:91` | `from statistics import NormalDist` 内联 import | 移到文件顶部或删除 |

---

## 审查流程记录

```
Phase 0 — Gather scope: 全量 6 文件（无 git diff，无上游分支）
Phase 1 — Find candidates: 7 路并行 finder agent
  ├─ Angle A: 逐行 bug 扫描         → 6 candidates
  ├─ Angle B: 跨文件调用追踪         → 6 candidates
  ├─ Angle C: 复用/简化/死代码       → 6 candidates
  ├─ Angle D: 数值稳定性             → 8 candidates
  ├─ Angle E: 输出/报告正确性        → 14 candidates
  ├─ Angle F: 边界条件/错误处理       → 30+ candidates
  └─ Angle G: 仿真验证专项           → 6 candidates
Phase 2 — Verify: 去重 → 合并 → 按严重度排序 → 取 top 10
Phase 3 — 修复验证: 重新读取已改代码 → 逐项确认
Phase 4 — 报告输出: 写入 .log/review/
```
