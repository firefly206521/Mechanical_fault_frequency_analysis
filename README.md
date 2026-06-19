# 机械设备故障检测 — 基于 GLRT 的弱正弦信号检测

数学建模竞赛 A 题子项目：在强噪声背景下检测机械设备微弱故障信号。

## 问题概述

机械设备运行时产生的振动信号中，微弱的周期性故障分量常被强背景噪声淹没。本题旨在设计信号处理方法，从含噪观测中检测并提取弱正弦故障频率。

## 方法

采用 **广义似然比检验（GLRT）** 作为核心检测方法：

1. **预处理** — 去直流 + 线性去趋势
2. **粗搜索** — 通过 FFT 频谱计算各频率点的 GLRT 统计量
3. **精修** — 在粗估频率附近用最小二乘做局部精修
4. **阈值控制** — 纯噪声 Monte Carlo 仿真确定检测门限（控制虚警率）
5. **判决** — GLRT 统计量超阈值则判定故障频率存在

## 项目结构

```
.
├── q1_glrt_model.py          # Q1 最终 GLRT 模型（主脚本）
├── q1_model_compare.py       # Q1 模型对比（多种频率检测方法对比）
├── q1_glrt/
│   ├── __init__.py           # 包初始化
│   └── core.py               # 核心计算函数
│
├── data.xlsx                 # 原始观测数据（.gitignore 忽略）
├── Single_fault_source.csv   # 单源故障导出数据（.gitignore 忽略）
├── Multiple_fault_sources.csv # 多源故障导出数据（.gitignore 忽略）
├── A题：机械设备故障检测.pdf  # 赛题原文（.gitignore 忽略）
│
├── q1_results/               # 模型对比输出（.gitignore 忽略）
├── q1_glrt_results/          # GLRT 模型输出（.gitignore 忽略）
│
├── README.md                 # 本文件
├── .gitignore
└── AGENTS.md                 # 本地工作流配置（.gitignore 忽略）
```

## 运行方式

```bash
# GLRT 全流程检测
python q1_glrt_model.py

# 模型对比（含 FFT / GLRT / 分段检测等）
python q1_model_compare.py
```

两个脚本均从 `data.xlsx` 中读取 `单源故障` sheet 的数据，输出结果写入 `q1_results/` 和 `q1_glrt_results/` 目录。

## 依赖

- Python ≥ 3.10
- numpy, scipy
- matplotlib
- pandas
- scikit-learn（仅模型对比脚本）

```bash
pip install numpy scipy matplotlib pandas scikit-learn
```

## 许可

本项目为数学建模竞赛代码，仅供学习参考。
