"""长文件分析策略：全量分析 / 抽样分析 / 截断。

为什么不简单粗暴地"只取前 600 秒"：
  1. 一首 7 分钟的歌不该被截断 —— 截断后 integrated LUFS 与 LRA 都是错的；
  2. 一小时的 DJ set 也不该被截断，但也没必要逐样本分析 —— 抽样同样准确；
  3. 24 bit / 192 kHz / 8 声道的 6 分钟素材，光解码数组就 1.4 GB，
     全量分析会把 12 GB 的机器拖进交换分区。
所以按"样本预算"（帧 × 声道）分三档，并把用了哪一档、为什么，如实告诉用户。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from . import config

# 抽样分析时的取段数：5 段足以覆盖前奏/主歌/副歌/尾奏，且每段都足够长到
# 让 3 秒短时响度块与 20 ms 帧能量统计稳定。
_SAMPLE_SEGMENTS = 5
_SAMPLE_SEG_MAX = 60.0     # 单段上限；预算不够时按预算缩小
_SAMPLE_SEG_MIN = 5.0      # 单段低于 5 秒就不抽样了，直接截断更诚实


@dataclass
class AnalysisPlan:
    mode: str = "full"          # full | sample | truncated
    seconds: float = 0.0        # 实际参与分析的时长
    total_seconds: float = 0.0  # 文件总时长
    segments: int = 1
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _budget_seconds(rate: int, nch: int) -> float:
    """样本预算换算成秒数：ANALYSIS_BUDGET_SAMPLES / (采样率 × 声道)。"""
    return config.ANALYSIS_BUDGET_SAMPLES / float(max(1, rate) * max(1, nch))


def plan_analysis(total_seconds: float, rate: int, nch: int) -> AnalysisPlan:
    rate = max(1, int(rate))
    nch = max(1, int(nch))
    total = max(0.0, float(total_seconds))
    plan = AnalysisPlan(total_seconds=round(total, 2))
    budget = _budget_seconds(rate, nch)
    cap = config.MAX_ANALYSIS_SECONDS

    # 档一：时长与体积都在预算内 —— 逐样本
    if total <= min(cap, budget):
        plan.mode = "full"
        plan.seconds = round(total, 2)
        plan.note = "全长逐样本分析"
        return plan

    # 档二：抽样。段的长度按预算缩，而不是硬取 60 秒
    seg_sec = min(_SAMPLE_SEG_MAX, budget / _SAMPLE_SEGMENTS)
    if total > cap and seg_sec >= _SAMPLE_SEG_MIN:
        plan.mode = "sample"
        plan.seconds = round(seg_sec * _SAMPLE_SEGMENTS, 2)
        plan.segments = _SAMPLE_SEGMENTS
        why = (f"文件长 {total / 60:.1f} 分钟，超过单次逐样本分析的 {cap / 60:.0f} 分钟上限"
               if total > cap else
               f"{rate / 1000:.1f} kHz × {nch} 声道的解码体积超出预算")
        plan.note = (f"{why}；已改为在时间轴上均匀抽取 {_SAMPLE_SEGMENTS} 段 × {seg_sec:.0f} 秒"
                     f"（共 {plan.seconds:.0f} 秒）做统计，响度/带宽/立体声结论依然代表整体。")
        return plan

    # 档三：预算太小，抽样也没意义 —— 只分析开头一段
    plan.mode = "truncated"
    plan.seconds = round(min(total, cap, budget), 2)
    plan.note = (f"文件长 {total / 60:.1f} 分钟，且 {rate / 1000:.1f} kHz × {nch} 声道的解码体积"
                 f"远超预算；只分析前 {plan.seconds:.0f} 秒，结论仅代表开头这一段。")
    return plan


def extract(y: np.ndarray, rate: int, plan: AnalysisPlan) -> np.ndarray:
    """按计划从解码结果里取出要分析的样本。

    y 可能是 memmap（codecs 对大文件自动落盘），切片不会触发整段读入。
    """
    n = int(y.shape[0])
    if plan.mode == "full":
        return np.asarray(y, dtype=np.float64)
    nch = int(y.shape[1]) if y.ndim > 1 else 1
    budget = min(n, max(1, int(plan.seconds * rate)))
    if plan.mode == "truncated":
        return np.asarray(y[:budget], dtype=np.float64)
    # sample：均匀取 segs 段，段内连续，段间跳跃
    segs = max(1, int(plan.segments))
    seg = max(1024, budget // segs)
    if seg * segs >= n:
        return np.asarray(y, dtype=np.float64)
    starts = np.linspace(0, n - seg, segs).astype(int)
    parts = [np.asarray(y[s:s + seg], dtype=np.float64).reshape(-1, nch) for s in starts]
    return np.concatenate(parts, axis=0)
