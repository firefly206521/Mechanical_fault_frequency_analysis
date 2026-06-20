# 全项目结果目录归档清理

> 日期：2026-06-20  
> 目的：删除重复/中间/旧版结果目录，每问只保留一份权威结果，无需读日志即可定位。

## 清理前状态

各问存在多版结果目录（原始版、优化前基线、中间测试、N=12000旧版等），定位权威目录需翻阅日志。

## 清理后权威目录

| 问 | 目录 | 说明 |
|----|------|------|
| Q1 | `q1_glrt_results_n40001/` | GLRT N=40001，FFT门限修复，随机频率，200 MC |
| Q1 | `q1_results_n40001/` | 多模型对比 N=40001 |
| Q2 | `q2_harmonic_recovery_results/` | 谐波恢复（唯一版本） |
| Q3 | `q3_multisource_separation_results_optimized/` | 优化版最终权威 |
| Q4 | `q4_sensor_layout_v1_results_robustness_v2_medium/` | V1 鲁棒性验证 medium 运行 |
| Q4 | `q4_adaptive_sensor_layout/` | V1 源码（V0 代码已归档） |

## 归档内容（`_archived/`）

```
_archived/
├── q1_glrt_results/                                    ← Q1 旧 N=12000
├── q1_results/                                         ← Q1 多模型旧 N=12000
├── q3_multisource_separation_results_review_fixed_large/ ← Q3 优化前基线
├── q3_archived_results_20260619/                       ← Q3 历史中间（4子目录）
├── q4_archived_results_20260620/                       ← Q4 V0结果+V1中间（9子目录）
└── q4_sensor_layout/                                   ← Q4 V0 源码
```

## 具体操作

1. Q1 旧 `q1_glrt_results/` `q1_results/` → `_archived/`（新 N=40001 目录文件齐全，无需迁移）
2. Q3 `review_fixed_large/` → `_archived/`（优化版为最终权威）
3. Q3 历史归档 `q3_archived_results_20260619/` → `_archived/`（合并）
4. Q4 V0 结果 `q4_sensor_layout_results/` `q4_sensor_layout_results_overnight/` → `_archived/`
5. Q4 V1 中间测试（7个目录）→ `_archived/`
6. Q4 V0 源码 `q4_sensor_layout/` → `_archived/`
7. 所有归档统一收入 `_archived/`
