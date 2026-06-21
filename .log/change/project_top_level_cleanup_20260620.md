# 顶层目录杂物清理

> 日期：2026-06-20  
> 目的：清理散落在项目根目录的生成数据、文档、临时文件，恢复顶层为包+结果+配置的简洁结构。

## 清理前状态

顶层散落了多个生成文件，来源包括：
- 脚本输出路径默认为 `./`，未写入对应结果目录
- 某次 `git diff` 重定向错误，把完整 Windows 路径当文件名写入
- Claude Code 自动生成的 `AGENTS.md`
- Python 缓存 `__pycache__/` 和临时测试 `tmp/`

## 清理后顶层

每个顶层条目都有明确归属：

| 条目 | 类型 | 归属 |
|------|------|------|
| `.claude/` | 配置 | Claude Code |
| `.log/` | 配置 | 项目变更日志 |
| `_archived/` | 归档 | 旧版结果合集 |
| `paper/` | 内容 | 论文源码+支撑文档+问题PDF |
| `q1_glrt/` `q1_glrt_results_n40001/` | Q1 | 包+权威结果 |
| `q1_glrt_model.py` `q1_model_compare.py` | Q1 | 入口脚本（硬编码路径引用，暂留顶层） |
| `q1_results_n40001/` | Q1 | 模型对比结果 |
| `q2_harmonic_recovery/` `q2_harmonic_recovery_results/` | Q2 | 包+权威结果 |
| `q3_multisource_separation/` | Q3 | 包 |
| `q3_multisource_separation_results_optimized/` | Q3 | 权威结果 |
| `q3_multisource_separation_results_optimized_complete/` | Q3 | 完整再生结果 |
| `q4_adaptive_sensor_layout/` | Q4 | V1 包 |
| `q4_sensor_layout_v1_results_robustness_v2_medium/` | Q4 | 权威结果 |
| `CLAUDE.md` `README.md` `data.xlsx` `.gitignore` | 配置 | 项目根必备 |

## 具体操作

| 操作 | 文件 | 原因 |
|------|------|------|
| 🗑️ 删除 | `C:UsersFirefly...q4_diff.py.diff` | 路径畸形的 bug 产物，完整 Windows 路径被当文件名写入 |
| 🗑️ 删除 | `AGENTS.md` | Claude Code 自动生成，已在 `.gitignore` |
| 🗑️ 删除 | `__pycache__/` | 顶层 `.py` 文件的 Python 缓存，已在 `.gitignore` |
| 🗑️ 删除 | `tmp/` | Q3 smoke test 临时输出，内容已在权威目录 |
| 📦 → `_archived/` | `Multiple_fault_sources.csv` | 从 `data.xlsx` 提取的数据，无脚本引用 |
| 📦 → `_archived/` | `Single_fault_sources.csv` | 同上（⚠️ 原文件被进程锁定未删，副本已归档） |
| 📦 → `_archived/` | `需要重跑的实验.md` | 顶层旧版（10538 字符），`paper/` 有更新版（11014 字符） |
| 📄 → `paper/` | `A题模型手册.md` | 模型手册，与论文相关 |
| 📄 → `paper/` | `强噪声下微弱故障信号检测报告.md` | 检测报告，与论文相关 |
| 📄 → `paper/` | `论文大纲.md` | 论文大纲 |
| 📄 → `paper/` | `A题：机械设备故障检测.pdf` | 赛题 PDF |

## 遗留问题

- `Single_fault_source.csv` 被外部进程（可能是 Excel）锁定，无法删除。关闭后手工清理即可，`_archived/` 已有备份。
- 顶层两个入口脚本 `q1_glrt_model.py` / `q1_model_compare.py` 是历史遗留（Q1 早于包规范建立），但 CLI 和文档均引用其顶层路径，暂不移动。
