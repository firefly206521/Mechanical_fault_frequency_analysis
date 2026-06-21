# Q3 实验组 G：敏感性分析

## 第一层：真实数据参数扫描
- 基线参数：α=0.05, ΔBIC=10, MC=500
- 检测分量数 K 稳定：是（观察值: [4]）
  - baseline: K=4, BIC=-184169.8, stop=GLRT below threshold
  - total_alpha=0.01: K=4, BIC=-184169.8, stop=GLRT below threshold
  - total_alpha=0.05: K=4, BIC=-184169.8, stop=GLRT below threshold
  - total_alpha=0.1: K=4, BIC=-184169.8, stop=GLRT below threshold
  - bic_delta=6.0: K=4, BIC=-184169.8, stop=GLRT below threshold
  - bic_delta=10.0: K=4, BIC=-184169.8, stop=GLRT below threshold
  - bic_delta=20.0: K=4, BIC=-184169.8, stop=GLRT below threshold
  - glrt_mc=200: K=4, BIC=-184169.8, stop=GLRT below threshold
  - glrt_mc=500: K=4, BIC=-184169.8, stop=GLRT below threshold
  - glrt_mc=1000: K=4, BIC=-184169.8, stop=GLRT below threshold

## 第二层：GLRT 门限 MC 稳定性
- α=0.05, MC=500 时门限 CV = 1.05%（3 种子）
  - α=0.01, MC= 100: threshold=28.1230 ± 1.3310 (CV=4.73%, range=9.32%)
  - α=0.01, MC= 200: threshold=28.4583 ± 0.2267 (CV=0.80%, range=1.44%)
  - α=0.01, MC= 500: threshold=28.5325 ± 0.2832 (CV=0.99%, range=1.98%)
  - α=0.01, MC=1000: threshold=28.5913 ± 0.2197 (CV=0.77%, range=1.53%)
  - α=0.01, MC=2000: threshold=28.9435 ± 0.4560 (CV=1.58%, range=3.03%)
  - α=0.01, MC=5000: threshold=29.1516 ± 0.4220 (CV=1.45%, range=2.57%)
  - α=0.05, MC= 100: threshold=25.9888 ± 0.8815 (CV=3.39%, range=6.49%)
  - α=0.05, MC= 200: threshold=25.3593 ± 0.5436 (CV=2.14%, range=3.96%)
  - α=0.05, MC= 500: threshold=25.5522 ± 0.2679 (CV=1.05%, range=1.94%)
  - α=0.05, MC=1000: threshold=25.6862 ± 0.1884 (CV=0.73%, range=1.46%)
  - α=0.05, MC=2000: threshold=25.7472 ± 0.2400 (CV=0.93%, range=1.86%)
  - α=0.05, MC=5000: threshold=25.7298 ± 0.0639 (CV=0.25%, range=0.49%)
  - α=0.1, MC= 100: threshold=24.4698 ± 1.0069 (CV=4.12%, range=7.39%)
  - α=0.1, MC= 200: threshold=24.1889 ± 0.9350 (CV=3.87%, range=7.73%)
  - α=0.1, MC= 500: threshold=24.1793 ± 0.4353 (CV=1.80%, range=3.43%)
  - α=0.1, MC=1000: threshold=24.3207 ± 0.3315 (CV=1.36%, range=2.73%)
  - α=0.1, MC=2000: threshold=24.3244 ± 0.2366 (CV=0.97%, range=1.94%)
  - α=0.1, MC=5000: threshold=24.2842 ± 0.1086 (CV=0.45%, range=0.89%)

## 第三层：精修搜索半径
- 最大频率偏移 = 8.85e-03 Hz
  - half_width=0.001: max_dev=6.92e-07, BIC=-184169.8
  - half_width=0.003: max_dev=6.42e-07, BIC=-184169.8
  - half_width=0.006: max_dev=1.28e-06, BIC=-184169.8
  - half_width=0.012: max_dev=8.85e-03, BIC=-179192.2
  - half_width=0.025: max_dev=8.88e-16, BIC=-184169.8

## 结论
- 检测分量数 K 对参数选择不敏感
- GLRT 门限在 MC=500 时变异系数约 1.0%
- 精修半径对最终频率影响 < 8.85e-03 Hz（需关注）