"""Generate paper-facing relationship and algorithm flowcharts."""

from __future__ import annotations

from pathlib import Path
import textwrap

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon


OUT_DIR = Path(__file__).resolve().parent
EDGE = "#50555A"
TEXT = "#222222"


def configure_font() -> None:
    for font_path in [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/Deng.ttf"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]:
        if font_path.exists():
            font_manager.fontManager.addfont(str(font_path))
            name = font_manager.FontProperties(fname=str(font_path)).get_name()
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def wrap(text: str, width: int = 11) -> str:
    output: list[str] = []
    for part in str(text).split("\n"):
        output.extend(textwrap.wrap(part, width=width, break_long_words=False, replace_whitespace=False) or [""])
    return "\n".join(output)


def canvas(figsize=(11.8, 7.0)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def save(fig, filename: str) -> None:
    fig.savefig(OUT_DIR / filename, dpi=300, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def node(ax, center, size, text, kind="process", fontsize=11):
    cx, cy = center
    w, h = size
    if kind == "terminator":
        patch = FancyBboxPatch(
            (cx - w / 2, cy - h / 2),
            w,
            h,
            boxstyle="round,pad=0.015,rounding_size=0.035",
            linewidth=1.6,
            edgecolor=EDGE,
            facecolor="white",
        )
    elif kind == "decision":
        points = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
        patch = Polygon(points, closed=True, linewidth=1.6, edgecolor=EDGE, facecolor="white")
    else:
        patch = FancyBboxPatch(
            (cx - w / 2, cy - h / 2),
            w,
            h,
            boxstyle="square,pad=0.015",
            linewidth=1.6,
            edgecolor=EDGE,
            facecolor="white",
        )
    ax.add_patch(patch)
    ax.text(cx, cy, wrap(text), ha="center", va="center", fontsize=fontsize, color=TEXT)


def arrow(ax, start, end, label: str | None = None, label_pos=0.5, offset=(0, 0), rad=0.0):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=13,
        linewidth=1.5,
        color=EDGE,
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(patch)
    if label:
        x = start[0] + (end[0] - start[0]) * label_pos + offset[0]
        y = start[1] + (end[1] - start[1]) * label_pos + offset[1]
        ax.text(x, y, label, ha="center", va="center", fontsize=10, color=TEXT, backgroundcolor="white")


def title(ax, text: str) -> None:
    ax.text(0.5, 0.965, text, ha="center", va="top", fontsize=18, weight="bold", color="black")


def draw_problem_relation() -> None:
    fig, ax = canvas((12.8, 6.8))
    title(ax, "四问关系图")

    y = 0.64
    xs = [0.14, 0.38, 0.62, 0.86]
    labels = [
        "Q1\n单源检测\n估计 f0",
        "Q2\n波形恢复\n估计 A、phi",
        "Q3\n多源分离\n估计 fk、Ak、phik",
        "Q4\n传感器布局\n优化三测点",
    ]
    for x, label in zip(xs, labels):
        node(ax, (x, y), (0.16, 0.15), label, "process", fontsize=11)
    arrow(ax, (0.22, y), (0.30, y), "f0", offset=(0, 0.035))
    arrow(ax, (0.46, y), (0.54, y), "模型扩展", offset=(0, 0.035))
    arrow(ax, (0.70, y), (0.78, y), "多源参数", offset=(0, 0.035))

    support_y = 0.30
    node(ax, (0.22, support_y), (0.22, 0.12), "数据来源\n单源 sheet: Q1/Q2\n多源 sheet: Q3", "process", fontsize=10.5)
    node(ax, (0.50, support_y), (0.22, 0.12), "共同统计基础\n正弦模型 + 高斯噪声\nGLRT / MC 门限", "process", fontsize=10.5)
    node(ax, (0.78, support_y), (0.22, 0.12), "验证口径\n真实数据稳定性\nSNR 扫描与误报率", "process", fontsize=10.5)
    arrow(ax, (0.22, support_y + 0.06), (0.14, y - 0.075), rad=-0.05)
    arrow(ax, (0.50, support_y + 0.06), (0.62, y - 0.075), rad=0.05)
    arrow(ax, (0.78, support_y + 0.06), (0.86, y - 0.075), rad=0.05)

    ax.text(
        0.5,
        0.12,
        "主线：检测 → 恢复 → 多源扩展 → 系统布局；后一问复用前一问的参数估计、统计检验和验证结果。",
        ha="center",
        fontsize=11.5,
        color=TEXT,
    )
    save(fig, "q_all_problem_relation.png")


def draw_q1_flow() -> None:
    fig, ax = canvas()
    title(ax, "Q1 GLRT 微弱周期信号检测流程图")
    node(ax, (0.10, 0.62), (0.12, 0.08), "开始", "terminator")
    node(ax, (0.28, 0.62), (0.18, 0.11), "读取单源数据\n校验采样间隔", "process")
    node(ax, (0.50, 0.62), (0.18, 0.11), "去均值、去趋势\n构造候选频率网格", "process")
    node(ax, (0.72, 0.62), (0.18, 0.11), "计算 GLRT 统计量\nT(f)", "process")
    node(ax, (0.72, 0.38), (0.18, 0.13), "Tmax 是否\n超过 MC 门限?", "decision")
    node(ax, (0.50, 0.20), (0.18, 0.11), "连续频率精修\n最小二乘估计 f0", "process")
    node(ax, (0.28, 0.20), (0.18, 0.11), "分段稳定性检验\n记录参数和图表", "process")
    node(ax, (0.10, 0.20), (0.12, 0.08), "输出 f0", "terminator")
    node(ax, (0.90, 0.38), (0.13, 0.08), "未检出", "terminator")
    arrow(ax, (0.16, 0.62), (0.19, 0.62))
    arrow(ax, (0.37, 0.62), (0.41, 0.62))
    arrow(ax, (0.59, 0.62), (0.63, 0.62))
    arrow(ax, (0.72, 0.565), (0.72, 0.445))
    arrow(ax, (0.81, 0.38), (0.835, 0.38), "否", offset=(0, 0.03))
    arrow(ax, (0.72, 0.315), (0.58, 0.235), "是", offset=(-0.02, 0.02))
    arrow(ax, (0.41, 0.20), (0.37, 0.20))
    arrow(ax, (0.19, 0.20), (0.16, 0.20))
    save(fig, "q1_glrt_algorithm_flow.png")


def draw_q2_flow() -> None:
    fig, ax = canvas()
    title(ax, "Q2 谐波回归恢复流程图")
    node(ax, (0.10, 0.62), (0.12, 0.08), "开始", "terminator")
    node(ax, (0.28, 0.62), (0.18, 0.11), "输入 Q1 频率 f0\n中心化时间轴", "process")
    node(ax, (0.50, 0.62), (0.18, 0.11), "构造 sin/cos\n谐波回归矩阵", "process")
    node(ax, (0.72, 0.62), (0.18, 0.11), "联合拟合\n频率、振幅、相位", "process")
    node(ax, (0.72, 0.38), (0.18, 0.13), "残差是否\n仍有显著周期?", "decision")
    node(ax, (0.90, 0.38), (0.14, 0.09), "调整模型\n或加入对照", "process")
    node(ax, (0.50, 0.20), (0.18, 0.11), "参数不确定性\n残差诊断", "process")
    node(ax, (0.28, 0.20), (0.18, 0.11), "窄带滤波/SSA\n一致性验证", "process")
    node(ax, (0.10, 0.20), (0.12, 0.08), "输出 s(t)", "terminator")
    arrow(ax, (0.16, 0.62), (0.19, 0.62))
    arrow(ax, (0.37, 0.62), (0.41, 0.62))
    arrow(ax, (0.59, 0.62), (0.63, 0.62))
    arrow(ax, (0.72, 0.565), (0.72, 0.445))
    arrow(ax, (0.81, 0.38), (0.83, 0.38), "是", offset=(0, 0.03))
    arrow(ax, (0.90, 0.425), (0.78, 0.59), rad=0.22)
    arrow(ax, (0.72, 0.315), (0.58, 0.235), "否", offset=(-0.02, 0.02))
    arrow(ax, (0.41, 0.20), (0.37, 0.20))
    arrow(ax, (0.19, 0.20), (0.16, 0.20))
    save(fig, "q2_harmonic_recovery_flow.png")


def draw_q3_flow() -> None:
    fig, ax = canvas()
    title(ax, "Q3 多源故障分离与定阶流程图")
    node(ax, (0.08, 0.70), (0.11, 0.08), "开始", "terminator")
    node(ax, (0.24, 0.70), (0.17, 0.11), "读取多源数据\n初始化残差 r=x", "process")
    node(ax, (0.45, 0.70), (0.18, 0.11), "对残差执行\nGLRT 全频扫描", "process")
    node(ax, (0.66, 0.70), (0.17, 0.13), "是否存在\n过门限峰?", "decision")
    node(ax, (0.87, 0.70), (0.13, 0.08), "结束", "terminator")
    node(ax, (0.66, 0.48), (0.18, 0.10), "拟合候选分量\n从残差中剥离", "process")
    node(ax, (0.66, 0.28), (0.17, 0.13), "BIC 是否\n接受新分量?", "decision")
    node(ax, (0.43, 0.28), (0.18, 0.10), "多频联合精修\n估计 f、A、phi", "process")
    node(ax, (0.20, 0.28), (0.15, 0.08), "输出分量", "terminator")
    arrow(ax, (0.135, 0.70), (0.155, 0.70))
    arrow(ax, (0.325, 0.70), (0.36, 0.70))
    arrow(ax, (0.54, 0.70), (0.575, 0.70))
    arrow(ax, (0.745, 0.70), (0.805, 0.70), "否", offset=(0, 0.035))
    arrow(ax, (0.66, 0.635), (0.66, 0.53), "是", offset=(0.035, 0))
    arrow(ax, (0.66, 0.43), (0.66, 0.345))
    arrow(ax, (0.575, 0.28), (0.52, 0.28), "是", offset=(0, 0.035))
    arrow(ax, (0.34, 0.28), (0.275, 0.28))
    arrow(ax, (0.745, 0.28), (0.87, 0.65), "否", offset=(0.03, 0.02), rad=-0.10)
    arrow(ax, (0.43, 0.33), (0.45, 0.645), "更新残差\n继续扫描", offset=(-0.09, 0.0), rad=-0.20)
    save(fig, "q3_multisource_algorithm_flow.png")


def draw_q4_flow() -> None:
    fig, ax = canvas()
    title(ax, "Q4 自适应传感器布局优化流程图")
    node(ax, (0.08, 0.70), (0.11, 0.08), "开始", "terminator")
    node(ax, (0.24, 0.70), (0.17, 0.11), "生成候选测点\n区域/坐标/方向", "process")
    node(ax, (0.45, 0.70), (0.18, 0.11), "计算复响应 h_mk\n和噪声方差", "process")
    node(ax, (0.66, 0.70), (0.18, 0.11), "白化响应评分\n预筛选候选点", "process")
    node(ax, (0.66, 0.48), (0.18, 0.10), "greedy + one-swap\n搜索三测点", "process")
    node(ax, (0.66, 0.28), (0.18, 0.13), "MC 验证是否\n满足 Pd/Pfa?", "decision")
    node(ax, (0.39, 0.28), (0.18, 0.10), "输出最优布局\n与性能曲线", "terminator")
    node(ax, (0.88, 0.48), (0.14, 0.09), "调整权重\n或候选集", "process")
    arrow(ax, (0.135, 0.70), (0.155, 0.70))
    arrow(ax, (0.325, 0.70), (0.36, 0.70))
    arrow(ax, (0.54, 0.70), (0.57, 0.70))
    arrow(ax, (0.66, 0.645), (0.66, 0.53))
    arrow(ax, (0.66, 0.43), (0.66, 0.345))
    arrow(ax, (0.57, 0.28), (0.48, 0.28), "是", offset=(0, 0.035))
    arrow(ax, (0.75, 0.28), (0.84, 0.44), "否", offset=(0.02, 0.035), rad=-0.08)
    arrow(ax, (0.88, 0.525), (0.75, 0.68), rad=0.16)
    save(fig, "q4_sensor_layout_algorithm_flow.png")


def main() -> None:
    configure_font()
    draw_problem_relation()
    draw_q1_flow()
    draw_q2_flow()
    draw_q3_flow()
    draw_q4_flow()


if __name__ == "__main__":
    main()
