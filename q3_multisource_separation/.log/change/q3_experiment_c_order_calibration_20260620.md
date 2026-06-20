# Q3 实验 C：完整 SIC+BIC 定阶校准

## Scope

本次只处理 `paper/需要重跑的实验.md` 中的实验 C，对应 review issue #46：
此前“0.20% 纯噪声误报率”只覆盖首步 GLRT，不代表完整 Q3 流程的最终定阶误报率。

本次新增独立入口，不修改 Q3 主算法：

```powershell
python -m q3_multisource_separation.run_q3_experiment_c
```

## Output

正式结果目录：

```text
q3_experiment_c_results/
|- README.md
|- paper/
|  |- q3_experiment_c_report.md
|  |- q3_experiment_c_null_false_alarm.csv
|  |- q3_experiment_c_order_accuracy.csv
|  `- q3_experiment_c_weak_strong.csv
`- raw/
   |- q3_experiment_c_null_trials.csv
   |- q3_experiment_c_order_trials.csv
   |- q3_experiment_c_weak_strong_trials.csv
   `- q3_experiment_c_runtime.json
```

## Parameters

- N = 40001, fs = 100 Hz。
- 噪声标准差 sigma = 0.1。
- 最大分量数 = 10。
- 总目标误报率 = 0.05，单轮 GLRT `p_fa = 0.005`。
- GLRT 阈值 Monte Carlo 次数 = 500。
- BIC 接受阈值 `Delta BIC = 10`。
- 随机种子基准 `SEED = 20260620`。

## Commands

Smoke 验证：

```powershell
python -m compileall q3_multisource_separation
python -m q3_multisource_separation.run_q3_experiment_c --profile smoke --workers 4 --output-dir q3_experiment_c_results_smoke
```

正式实验：

```powershell
python -m q3_multisource_separation.run_q3_experiment_c --profile official --workers 8 --output-dir q3_experiment_c_results
```

结果树检查：

```powershell
python C:\Users\Firefly\.codex\skills\paper-output-optimizer\scripts\check_result_tree.py q3_experiment_c_results
```

检查结果：`ok=true`，`paper_file_count=4`，`raw_file_count=4`。

## Results

### 子实验 1：K=0 纯噪声

- 重复次数：1000。
- 完整流程最终误报 `P(K_hat >= 1) = 0 / 1000 = 0.000%`。
- Wilson 95% CI：`[0.000%, 0.383%]`。

### 子实验 2：已知 K 定阶准确性

每个 K 重复 500 次，频率在 `[1, 15] Hz` 内随机生成且最小间隔不小于 1 Hz，振幅在 `[0.01, 0.1]` 内随机生成。

| 真实 K | 重复次数 | 欠估率 | 正确定阶率 | 过估率 | 条件频率 MAE/Hz |
|---:|---:|---:|---:|---:|---:|
| 1 | 500 | 0.000% | 100.000% | 0.000% | 1.96669e-05 |
| 2 | 500 | 0.000% | 100.000% | 0.000% | 2.24811e-05 |
| 3 | 500 | 0.000% | 100.000% | 0.000% | 2.05348e-05 |
| 4 | 500 | 0.000% | 100.000% | 0.000% | 1.99004e-05 |

### 子实验 3：弱强分量混合

K=4，其中一个弱分量 `A=0.005`，三个强分量 `A=0.03-0.05`。每个弱强间距重复 200 次。

| 弱分量到最近强分量间距/Hz | 重复次数 | 弱分量检测率 | 正确定阶率 | 过估率 |
|---:|---:|---:|---:|---:|
| 0.5 | 200 | 65.500% | 65.500% | 0.000% |
| 1.0 | 200 | 67.500% | 67.500% | 0.000% |
| 2.0 | 200 | 68.000% | 68.000% | 0.000% |
| 5.0 | 200 | 69.500% | 69.500% | 0.000% |

## Paper Wording

论文中 Q3 的误报率应写为完整流程最终定阶误报率：

> 在 K=0 纯噪声条件下，完整 GLRT-SIC-联合精修-BIC 流程 1000 次 Monte Carlo 未产生最终分量误检，经验误报率为 0.000%，Wilson 95% 上界约 0.383%。此前首步 GLRT 的 0.20% 只能作为第一轮扫描越阈率，不能单独代表最终模型误报率。

弱强混合结果应作为检测边界讨论：当最弱分量振幅仅为 0.005 且噪声标准差为 0.1 时，完整流程不会明显过估强分量伪峰，但弱分量漏检仍存在，检测率约 65.5%-69.5%。

## Review Issue

`paper/review_issues.json` 中 #46 已更新为 `completed=true`。
