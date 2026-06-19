# Q1 第一阶段与 GLRT 重构变更日志

> 记录时间：2026-06-19  
> 工作目录：`E:\AIworkspace\2026CSU-math\testA`  
> 范围：Q1 单源故障微弱周期信号检测；不包含 Q2/Q3/Q4 多故障源扩展。

## 一、第一阶段完成事项

### 1. 题目与数据确认

- 阅读并参考 `A题模型手册.md`、`强噪声下微弱故障信号检测报告.md`。
- 确认 Q1 只处理 `data.xlsx` 的 `单源故障` sheet。
- 校验数据规模与采样信息：
  - 样本数约 `40001`
  - 采样间隔约 `0.01 s`
  - 采样率约 `100 Hz`
  - 总时长约 `400 s`
- 识别 Q1 信号模型为单一弱正弦周期信号：

  $$x(t)=A\sin(2\pi f_0t+\phi_0)+n(t).$$

### 2. 多模型比较脚本

- 新增并实现 `q1_model_compare.py`。
- 第一版实现并比较以下模型：
  - FFT Peak Baseline
  - Welch PSD
  - CFAR + FFT
  - Matched Filter / GLRT
  - SSA Denoise + FFT
  - MUSIC
- 统一模型输入、输出字段与频率精修逻辑。
- 生成比较输出到 `q1_results/`，包括 CSV、Markdown 和图表。
- 经比较后，选择 GLRT 作为 Q1 主模型。

### 3. Q1 GLRT 主模型

- 新增并实现 `q1_glrt_model.py`。
- 完成 GLRT 主流程：
  - 读取 `data.xlsx` / `单源故障`
  - 线性去趋势
  - 候选频率网格扫描
  - 计算 GLRT 统计量
  - Monte Carlo 估计阈值
  - 频率峰值定位
  - 最小二乘局部精修 `f0`
  - 输出检测结论
- 固定并记录主要参数：
  - `f_min = 0.05 Hz`
  - `f_max = 49.5 Hz`
  - `P_FA = 0.05`
  - `glrt_mc = 500`
  - `random_seed = 20260619`
  - 频率精修窗口：`max(3*fs/N, 0.01)`

### 4. Q1 完整收尾材料

- 增加数据预处理与噪声分析。
- 将 400 秒数据切分为 50 秒一段，验证每段均能检测到约 `2 Hz`。
- 构造不同 SNR 的正弦加噪声仿真数据。
- 比较 FFT 峰值法与 GLRT 的：
  - 检测概率
  - 频率估计误差
  - 低 SNR 稳定性
- 绘制检测概率 `P_D` - `SNR` 曲线。
- 生成 Q1 报告所需的公式、流程图、结果表和结论。
- 正式输出目录为 `q1_glrt_results/`。

### 5. 图表修正

- 修正早期图像问题：
  - `q1_glrt_statistic.png` 改为全频段对数图 + 峰值附近局部放大图，避免 Y 轴尺度压扁主峰。
  - `q1_glrt_recovered_signal_full.png` 改为前 10 秒窗口展示，避免 400 秒全时段红线过密导致整片发红。
- 图例、标题、坐标轴除专有名词外改为中文。
- 配置中文字体优先级：
  - Microsoft YaHei
  - SimHei
  - SimSun

## 二、拆分重构

### 1. 拆分目标

原 `q1_glrt_model.py` 同时包含：

- 数值计算
- 仿真评估
- CSV 输出
- Markdown 报告输出
- 图像生成
- CLI 参数解析

为降低单文件复杂度，将其拆成一个小包，并保留原入口兼容。

### 2. 新结构

- `q1_glrt_model.py`
  - 兼容入口。
  - 保留 `python .\q1_glrt_model.py ...` 的运行方式。
  - 对旧脚本可能引用的函数做 re-export。
- `q1_glrt/core.py`
  - GLRT 计算、FFT 对照、频率精修、分段验证、仿真、噪声分析。
  - 不负责生成文件和图片。
- `q1_glrt/outputs.py`
  - CSV、Markdown 报告、图片生成。
  - 不负责核心算法决策。
- `q1_glrt/cli.py`
  - 命令行参数解析。
  - 编排计算流程与输出流程。
- `q1_glrt/__init__.py`
  - 包标记。

## 三、审查报告后的修复

审查报告位置：

`E:\AIworkspace\2026CSU-math\testA\q1_glrt\.log\review\code_review.md`

### 1. 修复双重预处理

- 问题：`q1_glrt/core.py` 调用 `glrt_stat_from_fft()` / `fft_spectrum()` 前已经 `preprocess(x)`，而底层函数内部也会 `preprocess()`。
- 影响：检测统计量和阈值校准管线不一致。
- 修复：
  - GLRT 和 FFT 谱计算统一传入原始 `x`。
  - 只在最小二乘拟合、残差分析等需要显式预处理的位置使用 `preprocess(x)`。

### 2. 修复空频段崩溃

- 问题：当 `[f_min, f_max]` 与频率网格无交集时，`np.argmax([])` 会抛出不清晰错误。
- 修复：
  - 新增频段检查函数。
  - 无可用频点时抛出明确错误：

    `No frequency bins in search range [...] Hz. Check --f-min/--f-max against the sampling rate.`

- 同步修复：
  - `q1_glrt/core.py`
  - `q1_model_compare.py`

### 3. 修复 SNR 极值崩溃

- 问题：`signal_power = 0` 或 `residual_power = 0` 时，`math.log10()` 或除零会崩溃。
- 修复：
  - 当信号功率或残差功率小于等于 0 时，`estimated_snr_db` 返回 `NaN`。

### 4. 减少重复读取 Excel

- 问题：一次运行中多处重复 `pd.read_excel`。
- 修复：
  - 在 `q1_glrt/core.py` 新增 `load_q1_data()`。
  - 使用 `lru_cache(maxsize=4)` 按绝对路径缓存数据。
  - `core.py` 与 `outputs.py` 均复用该入口。

### 5. 删除重复仿真函数

- 问题：`q1_glrt/core.py` 与 `q1_model_compare.py` 中 `synthetic_signal()` 重复。
- 修复：
  - `q1_glrt/core.py` 改为从 `q1_model_compare.py` 复用 `synthetic_signal()`。

### 6. 去掉无意义 Config 克隆

- 问题：分段验证循环内构造 `Config(**{**cfg.__dict__, ...})`，但没有实际改变配置。
- 修复：
  - 直接传入 `cfg`。

### 7. 兼容旧函数名

- 拆分后参数表函数名为 `build_parameter_table()`。
- 为避免旧脚本导入失败，在 `q1_glrt_model.py` 增加：

  ```python
  write_parameter_table = build_parameter_table
  ```

## 四、当前主要输出文件

正式结果目录：

`E:\AIworkspace\2026CSU-math\testA\q1_glrt_results`

主要文件包括：

- `q1_glrt_report.md`
- `q1_glrt_result.csv`
- `q1_glrt_parameters.csv`
- `q1_preprocessing_noise_analysis.csv`
- `q1_segment_validation.csv`
- `q1_fft_vs_glrt_simulation.csv`
- `q1_glrt_statistic.png`
- `q1_glrt_fft_baseline.png`
- `q1_glrt_recovered_overlay_zoom.png`
- `q1_glrt_recovered_signal_full.png`
- `q1_preprocessing_noise_analysis.png`
- `q1_segment_frequency_validation.png`
- `q1_pd_snr_curve.png`
- `q1_frequency_error_snr_curve.png`

## 五、关键结果

正式 Q1 GLRT 主结论：

- 检测结论：存在显著微弱周期故障信号。
- 粗估频率：约 `1.9999500013 Hz`
- 精修频率：约 `2.0000015345 Hz`
- GLRT 统计量：约 `2328.6571`
- 目标误报率：`P_FA = 0.05`
- 估计信噪比：约 `-12.08 dB`

## 六、验证记录

### 1. 拆分后语法检查

```powershell
python -m py_compile .\q1_glrt_model.py .\q1_glrt\__init__.py .\q1_glrt\core.py .\q1_glrt\outputs.py .\q1_glrt\cli.py .\q1_model_compare.py
```

结果：通过。

### 2. 拆分后快速运行

```powershell
python .\q1_glrt_model.py --glrt-mc 20 --sim-mc 2 --segment-seconds 50 --output-dir q1_glrt_results_refactor_check
```

结果：运行成功，检测频率保持为约 `2.0000015345 Hz`。

### 3. 审查修复后快速运行

```powershell
python .\q1_glrt_model.py --glrt-mc 20 --sim-mc 2 --segment-seconds 50 --output-dir q1_glrt_results_review_check
```

结果：运行成功，检测频率保持为约 `2.0000015345 Hz`。

### 4. 非法频段检查

```powershell
python .\q1_glrt_model.py --glrt-mc 5 --sim-mc 1 --f-min 60 --f-max 70 --output-dir q1_glrt_results_invalid_check
```

结果：按预期抛出明确错误，说明搜索频段与采样率对应的频率网格无交集。

### 5. 临时验证目录

以下临时目录仅用于验证，验证后已删除：

- `q1_glrt_results_refactor_check`
- `q1_glrt_results_review_check`
- `q1_glrt_results_invalid_check`

正式输出目录 `q1_glrt_results/` 未在审查修复过程中重生成或删除。

## 七、未处理或暂缓项

- `GLRT_PARAMETERS` 与 `build_parameter_table()` 存在信息重复，但仍作为旧接口 re-export，暂不删除。
- `run_glrt_q1()` 与 `glrt_detect_signal()` 的字典字段名仍不完全一致，当前分别服务最终报告与分段/仿真检测，暂不做破坏性统一。
- `2.0 Hz` 参考值仍用于 Q1 分段误差和图中参考线，因为当前 Q1 已确认故障频率约为 2 Hz；若后续要泛化到其他题目，可再参数化。
- `configure_plot_fonts()` 仍修改 matplotlib 全局字体配置；当前脚本是一次性生成报告图表的 CLI，用全局配置更简单，暂不引入上下文管理器。

