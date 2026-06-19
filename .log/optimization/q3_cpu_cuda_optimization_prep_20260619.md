# 第三问 CPU 多进程与 CUDA 优化准备

日期：2026-06-19

背景：第三问测试正在运行，预计 45-60 分钟。当前目标不是马上重写代码，而是提前准备优化路线、候选工具、判据和后续接入方式。等测试完成并拿到耗时分布后，再决定优先做 CPU 多进程、向量化、缓存，还是 CUDA/GPU。

## 1. 本机环境快照

当前在 `E:\AIworkspace\2026CSU-math\testA` 下检查到：

- CPU 逻辑核数：`32`
- NVIDIA GPU：可用
- 驱动显示 CUDA 版本：`12.8`
- GPU 显存：约 `8 GB`
- 已安装 Python 包：
  - `numpy`
  - `scipy`
  - `pandas`
  - `joblib`
  - `numba`
  - `dask`
- 未安装 Python 包：
  - `cupy`
  - `py-spy`
  - `scalene`
  - `line_profiler`

结论：

- CPU 多进程优化可以马上做。
- Numba CPU/JIT 也可以尝试。
- Dask 可用，但对本题这种单机竞赛脚本，不应作为第一选择。
- CUDA 路线具备硬件条件，但缺少 CuPy，需要额外安装与 CUDA 12.x 匹配的包。

## 2. 外部资料与候选工具

### 2.1 CPU 多进程

资料：

- Python 官方 `multiprocessing`
  - https://docs.python.org/3/library/multiprocessing.html
  - 适合把同一个函数分发到多个进程，做数据并行。
  - 官方文档建议简单数据并行可用 `Pool.map()`，更高层接口可用 `concurrent.futures.ProcessPoolExecutor`。

- Joblib
  - https://joblib.readthedocs.io/en/stable/parallel.html
  - 适合把 for-loop 中相互独立的任务改成并行。
  - 语法比原生 multiprocessing 更轻，适合 Monte Carlo、参数扫描、不同窗口/不同候选频率的独立计算。

优先建议：

1. 如果第三问耗时来自 Monte Carlo、参数网格、候选故障源组合扫描，优先用 `joblib.Parallel`。
2. 如果需要更精细控制进程、进度、异常和结果聚合，再用 `concurrent.futures.ProcessPoolExecutor`。
3. Windows 下多进程必须把入口放在：

   ```python
   if __name__ == "__main__":
       main()
   ```

### 2.2 Profiling

资料：

- py-spy
  - https://github.com/benfred/py-spy
  - 采样 profiler，可 attach 到正在运行的 Python 进程，不需要改代码。
  - 适合当前这种长时间运行脚本，用来确认热点函数。

- Scalene
  - https://github.com/plasma-umass/scalene
  - CPU/GPU/内存 profiler。
  - 适合后续判断是 Python 循环慢、原生库慢，还是内存分配/拷贝慢。

- line_profiler
  - https://kernprof.readthedocs.io/
  - 逐行 profiling。
  - 适合已经知道慢函数后，细看每一行。

当前本机未安装这些 profiler。若需要，推荐先安装 `py-spy` 或 `line_profiler`，不要一开始装一堆工具。

### 2.3 GPU/CUDA

资料：

- CuPy 官方文档
  - https://docs.cupy.dev/en/stable/overview.html
  - NumPy/SciPy 兼容的 GPU array 库，支持 CUDA/ROCm。
  - 适合大数组、线性代数、FFT、批量随机数、矩阵分解、批量 Monte Carlo。

- Numba CUDA
  - https://numba.readthedocs.io/en/stable/cuda/index.html
  - 注意：Numba 内置 CUDA target 已迁移到 NVIDIA `numba-cuda` 项目。
  - 适合需要自定义 CUDA kernel 的算法，不适合作为第一步。

- NVIDIA CUDA Samples
  - https://github.com/nvidia/cuda-samples
  - 包含 CUDA Python 示例，例如 deviceQuery、FFT、stream overlap、NumPy vs CuPy。

- 外部 GPU 优化 skill 参考
  - https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/scientific-skills/optimize-for-gpu/SKILL.md
  - 该 skill 的核心判断可借鉴：
    - CuPy：优先用于 NumPy/SciPy 风格的大数组、FFT、线性代数、Monte Carlo。
    - Numba CUDA：用于无法表达成数组操作的自定义并行核。
    - 先判断代码形态，再选 GPU 库。

本题优先级：

1. CuPy 只在主耗时是大规模数组运算、批量 FFT、批量 Monte Carlo 时值得。
2. Numba CUDA 只有在热点是自定义逐点/逐组合计算，且能批量并行时再考虑。
3. 如果热点是 Python 控制流、小数组循环、Excel/CSV/绘图，CUDA 不会是第一解。

### 2.4 Dask

资料：

- Dask 官方文档
  - https://docs.dask.org/
  - 支持本地/分布式并行计算。

本题判断：

- Dask 适合复杂任务图、超内存数组、分布式或需要 dashboard 的流程。
- 第三问如果只是单机脚本、参数扫描、Monte Carlo，`joblib` 更轻。
- 除非第三问已经形成大量任务图或数据超过内存，否则暂不建议引入 Dask。

## 3. 第三问跑完后必须先拿到的证据

不要直接上 CUDA。测试跑完后，先让第三问脚本输出或补充以下信息：

1. 总运行时间。
2. 各阶段耗时：
   - 数据读取
   - 预处理
   - 主算法
   - 参数扫描
   - Monte Carlo/Bootstrap
   - SSA/SVD/矩阵分解
   - 绘图/报告生成
3. 最慢的 5 个函数。
4. 主要循环的次数：
   - SNR 数
   - Monte Carlo runs
   - 候选频率数
   - 候选故障源/组合数
   - 分段数
5. 每个任务是否互相独立。
6. 单个任务输入/输出大小。
7. 是否存在重复计算：
   - 重复读 Excel
   - 重复构建设计矩阵
   - 重复 FFT
   - 重复生成随机噪声
   - 重复拟合同一频率网格

建议先加入轻量计时器：

```python
import time
from contextlib import contextmanager

@contextmanager
def timer(name, stats):
    start = time.perf_counter()
    yield
    stats[name] = stats.get(name, 0.0) + time.perf_counter() - start

def print_timing(stats):
    total = sum(stats.values())
    for name, seconds in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        pct = seconds / total * 100 if total else 0.0
        print(f"{name}: {seconds:.2f}s ({pct:.1f}%)")
```

## 4. 决策树

### 4.1 先优化 CPU 的情况

满足任一条件，先不碰 CUDA：

- 单次任务数组规模不大，但循环次数很多。
- 主要耗时在 Python for-loop。
- 每个任务互相独立。
- 输出只是少量标量或小数组。
- 运行时间 45-60 分钟，但没有证明热点是大规模数组核。

优先操作：

1. 缓存重复计算。
2. NumPy 向量化。
3. `joblib.Parallel(n_jobs=...)` 并行外层独立任务。
4. 必要时用 `numba.njit` 优化纯数值循环。

### 4.2 考虑 CuPy/CUDA 的情况

满足以下多数条件，才考虑 CUDA：

- 单次或批量数组规模大。
- 主要耗时是 FFT、矩阵乘法、SVD、线性代数、批量随机数、批量谱计算。
- 能把一整批任务留在 GPU 上计算，避免频繁 CPU/GPU 来回拷贝。
- 输出结果可以最后一次性拷回 CPU。
- 预计 CPU 多进程仍然超过 30 分钟。

优先操作：

1. 先写一个 CuPy 小原型，只覆盖最慢的核。
2. 只比较一个阶段，不要一次性迁移全 pipeline。
3. 验证数值误差、随机种子、dtype。
4. 再决定是否正式接入。

### 4.3 不建议 CUDA 的情况

以下情况不建议 CUDA：

- 慢在 Excel/CSV 读写。
- 慢在 Matplotlib/图片生成/Markdown 报告。
- 慢在很多小数组的 scipy optimizer 调用。
- 每个任务都要频繁把数据从 CPU 传到 GPU 再传回来。
- 代码没有明确热点，只是“感觉慢”。

## 5. 针对本题的候选优化方案

### 方案 A：最小侵入 CPU 多进程

适用：

- 第三问是多故障源、多组合、多频率、多窗口扫描。
- 每个候选组合可独立计算评分。

形态：

```python
from joblib import Parallel, delayed

def evaluate_one(candidate):
    return candidate, compute_score(candidate)

results = Parallel(n_jobs=-2, verbose=10)(
    delayed(evaluate_one)(candidate)
    for candidate in candidates
)
```

注意：

- 不要把巨大数组复制到每个任务里。
- 共享大数组时，优先把数据作为只读全局或使用 joblib memmap。
- Windows 下注意入口保护。

### 方案 B：批量向量化

适用：

- 大量候选频率/相位/幅值网格。
- 每个候选都做类似投影、残差、相关、能量评分。

形态：

```python
angles = 2.0 * np.pi * freqs[:, None] * t[None, :]
sin_bank = np.sin(angles)
cos_bank = np.cos(angles)
scores = (sin_bank @ x) ** 2 + (cos_bank @ x) ** 2
```

注意：

- 可能占内存，需按 frequency chunk 分块。
- 如果向量化后数组很大，再考虑 CuPy。

### 方案 C：Numba CPU JIT

适用：

- 热点是纯 Python 数值循环。
- 循环逻辑不容易写成 NumPy。

形态：

```python
from numba import njit, prange

@njit(parallel=True, fastmath=True)
def scan_candidates(...):
    for i in prange(n):
        ...
```

注意：

- 不适合包含 pandas、openpyxl、复杂 Python 对象的代码。
- 先对单个热点函数试，不要全项目改。

### 方案 D：CuPy GPU 原型

适用：

- 批量 FFT、批量 GLRT/投影、批量 Monte Carlo。

可能安装命令：

```powershell
pip install cupy-cuda12x
```

最小验证：

```python
import cupy as cp

x = cp.asarray(x_cpu)
freq = cp.fft.rfft(x)
power = cp.abs(freq) ** 2
power_cpu = cp.asnumpy(power)
```

注意：

- 当前 GPU 显存约 8 GB，要避免一次性构造过大的二维矩阵。
- CuPy 安装必须和 CUDA/驱动兼容。
- 若只做 40001 点单次 FFT，不值得上 GPU。

## 6. 建议执行顺序

测试跑完后建议按以下顺序执行：

1. 记录当前总运行时间和输出是否正确。
2. 加阶段计时器，重新跑一次小规模参数。
3. 找出最慢阶段。
4. 如果慢在独立任务循环，先用 `joblib` 并行外层。
5. 如果慢在 Python 数值循环，尝试 `numba.njit`。
6. 如果慢在大规模数组/FFT/矩阵，尝试 CuPy 小原型。
7. 每次优化都保存：
   - 优化前时间
   - 优化后时间
   - 输出关键数值差异
   - 是否改变报告结论

## 7. 推荐给另一个 AI 的最小要求

让正在写第三问的 AI 在测试完成后至少给出：

```text
总耗时：
最慢阶段：
最慢函数：
主要循环维度：
是否可独立并行：
每次任务输入数据大小：
输出关键结果：
```

如果它能修改代码，建议先输出：

```text
timing.csv
profile_summary.md
```

其中 `timing.csv` 至少包含：

```csv
stage,seconds,percent,notes
```

## 8. 当前结论

以现有信息判断：

- 45-60 分钟已经值得优化。
- 第一优先级不是 CUDA，而是 profiling + CPU 多进程。
- 本机 32 逻辑核，`joblib` 已安装，CPU 并行收益很可能比 CUDA 接入更快落地。
- CUDA 有硬件条件，但缺少 CuPy；只有在热点明确为批量数组/FFT/Monte Carlo 后才建议安装并原型验证。
- 如果第三问结果显示主耗时是独立候选扫描，直接做 `joblib.Parallel`。
- 如果主耗时是大矩阵/SVD/批量 FFT，再考虑 CuPy。

## 9. 资料链接

- Python multiprocessing: https://docs.python.org/3/library/multiprocessing.html
- Joblib Parallel: https://joblib.readthedocs.io/en/stable/parallel.html
- CuPy overview: https://docs.cupy.dev/en/stable/overview.html
- Numba CUDA: https://numba.readthedocs.io/en/stable/cuda/index.html
- NVIDIA CUDA samples: https://github.com/nvidia/cuda-samples
- py-spy: https://github.com/benfred/py-spy
- Scalene: https://github.com/plasma-umass/scalene
- Dask: https://docs.dask.org/
- GPU optimization skill reference: https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/scientific-skills/optimize-for-gpu/SKILL.md
