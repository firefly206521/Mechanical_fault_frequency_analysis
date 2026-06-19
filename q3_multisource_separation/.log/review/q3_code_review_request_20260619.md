# Q3 代码质量审查任务单

日期：2026-06-19

用途：交给另一个 AI 对第三问代码做代码质量审查。只输出审查报告，不直接修改代码。

## 审查范围

重点审查代码：

- `q3_multisource_separation/core.py`
- `q3_multisource_separation/experiments.py`
- `q3_multisource_separation/cli.py`
- `q3_multisource_separation/outputs.py`
- `q3_multisource_separation/run_q3.py`
- `q3_multisource_separation/README.md`

参考输出目录：

- `q3_multisource_separation_results/`

重点参考结果文件：

- `q3_runtime.txt`
- `q3_report.md`
- `q3_global_parameters.csv`
- `q3_detected_components.csv`
- `q3_model_selection.csv`
- `q3_simulation_trials.csv`
- `q3_simulation_validation.csv`
- `q3_resolution_trials.csv`
- `q3_resolution_limit.csv`
- `q3_null_trials.csv`
- `q3_music_comparison.csv`

## 审查重点

### 1. 正确性

- 多峰 GLRT 顺序检测是否会漏检或误停。
- BIC 接受条件是否和报告描述一致。
- `max_components`、`p_fa_step`、`glrt_mc` 的含义是否一致。
- `detect_multitone()` 中候选 seed、split、refine 逻辑是否可能错过更优分量。
- 近频 `close_pair_resolver()` 与 `music_close_pair()` 的成功判据是否合理。
- `estimated_k`、频率匹配、振幅误差、相位误差统计是否存在排序错配。
- 多频联合最小二乘的设计矩阵、参数个数、BIC 公式是否正确。
- 条件数、数值秩、ill-conditioned 标记是否和最终结论一致。

### 2. 实验统计

- `simulation_runs`、`resolution_runs`、`null_runs` 的实际输出行数是否正确。
- `--resume` 是否只补缺失 replicate，不重复、不漏算。
- 随机种子是否保证可复现，且不同实验、不同 replicate 之间不相关。
- Wilson 区间计算是否正确。
- K 识别正确率、误报率、近频成功率、经验分辨极限计算是否正确。
- `priority_for_more_runs` 判据是否符合报告含义。
- `summarize_simulation()` 是否正确处理 `NaN`、错误 K、空组。
- `summarize_resolution()` 是否正确按振幅条件和频率间隔分组。

### 3. 性能与耗时

- 当前 `q3_runtime.txt` 阶段耗时是否完整可信。
- 是否需要额外输出结构化 `q3_timing.csv`。
- 最慢函数或最慢阶段是否能从现有 runtime 中定位。
- 是否存在明显重复计算：
  - 重复构建设计矩阵；
  - 重复 FFT；
  - 重复 GLRT threshold Monte Carlo；
  - 重复读取 CSV；
  - 重复生成相同时间轴或频率网格；
  - 每 20 次写盘是否合适。
- 200 次运行前是否有必须修复的性能问题。
- 是否适合先 CPU 多进程，而不是 CUDA。

### 4. 边界条件

- 空 CSV、半截 CSV、resume 中断恢复。
- `simulation_runs=0`、`resolution_runs=0`、`null_runs=0`。
- `--skip-simulation`、`--skip-resolution`、`--skip-null` 后报告是否还能生成。
- 近频完全不可分、条件数过大、rank 不足时是否有明确标记。
- 无 Chrome/Edge 时图片转换是否会丢 SVG 或静默失败。
- Excel 数据为空、NaN、Inf、文本时是否有明确错误。
- 输出目录已有旧文件时，非 resume 模式是否正确清理 trial CSV。

### 5. 输出一致性

- CSV 字段名是否稳定。
- `q3_report.md` 是否和 CSV 数值一致。
- `README.md` 中命令、默认参数、耗时说明是否和代码一致。
- 图表中文标签和专有名词是否符合前两问风格。
- `q3_runtime.txt` 的 `estimated_full_200_seconds` 是否按当前参数正确估算。
- `q3_runtime.txt` 中 completed rows 是否与 CSV 行数一致。
- 图片生成数量是否和 runtime 中 `png_count` 一致。

### 6. 代码质量

- 是否有未使用变量或未使用导入。
- 是否有硬编码本机路径。
- 是否有平台相关问题，尤其是 Windows 多进程入口和路径编码。
- 是否有函数职责过大但不影响当前任务。
- 是否有应该先不改、只记录的低优先级问题。
- 是否有与 Q1/Q2 模块重复但容易漂移的逻辑。

## 输出格式要求

建议输出 Markdown，文件名建议：

`q3_multisource_separation/.log/review/code_review_20260619.md`

报告格式：

```markdown
# Q3 Code Review

## Summary

- 总体判断：
- 是否建议先跑 200 次：
- 是否存在阻塞级问题：
- 建议先修复数量：
- 可延后修复数量：

## Findings

### P0 / P1 / P2 / P3 - 标题

- 文件：
- 行号：
- 严重度：
- 类型：
- 问题：
- 影响：
- 复现场景：
- 建议修复：
- 是否阻塞 200 次测试：

## Suggested Order

1. 必须先修：
2. 可在 200 次后修：
3. 只记录不修：

## Runtime Notes

- 当前耗时输出是否够用：
- 是否建议增加 `q3_timing.csv`：
- 预计主要瓶颈：
- CPU 多进程是否值得：
- CUDA 是否值得：
```

如果输出 JSON，建议至少包含：

```json
{
  "summary": {
    "overall": "",
    "block_200_run": false,
    "must_fix_before_200": 0,
    "can_fix_after_200": 0
  },
  "findings": [
    {
      "id": "Q3-001",
      "severity": "P1",
      "file": "q3_multisource_separation/core.py",
      "line": 0,
      "category": "correctness",
      "title": "",
      "detail": "",
      "impact": "",
      "repro": "",
      "fix": "",
      "blocks_200_run": true
    }
  ],
  "runtime_notes": {
    "timing_output_sufficient": true,
    "recommend_q3_timing_csv": false,
    "main_bottleneck": "",
    "recommend_cpu_parallel": false,
    "recommend_cuda": false
  }
}
```

## 分级标准

- `P0`：会导致结果错误、运行失败、数据丢失，必须在 200 次前修。
- `P1`：明显影响统计结论或可复现性，原则上 200 次前修。
- `P2`：影响健壮性、可维护性或部分边界场景，可在 200 次后修。
- `P3`：风格、轻微重复、文档小问题，只记录即可。

## 当前已知背景

当前 10 次小规模运行结果：

- 总耗时：约 `43 s`
- `simulation_target_runs=10`
- `resolution_target_runs=10`
- `null_target_runs=50`
- `simulation_completed_rows=50`
- `resolution_completed_rows=240`
- `null_completed_rows=50`
- `estimated_full_200_seconds≈646 s`
- 主要耗时阶段：多源仿真，其次近频实验。

当前建议顺序：

1. 先完成代码质量审查。
2. 修复会影响结果正确性的 `P0/P1`。
3. 补强时间输出。
4. 做一次轻量测试。
5. 跑 200 次 baseline。
6. 根据 200 次耗时再优化运行逻辑。
