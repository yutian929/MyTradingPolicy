"""Find disjoint historical windows resembling the latest closing-price path."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


def period_label(rank):
    return chr(0x2460 + rank - 1) if 1 <= rank <= 20 else str(rank)


@dataclass(frozen=True)
class SimilarPeriod:
    start: pd.Timestamp
    end: pd.Timestamp
    score: float


def find_similar_periods(frame, m, n):
    """Rank positive Pearson correlations; all windows stay inside frame.

    Compare rebased close paths, not daily returns. Greedy suppression keeps
    the strongest candidate and removes any overlapping historical windows.
    """
    if m < 3 or n < 1:
        raise ValueError("M 至少为 3，N 至少为 1。")
    if len(frame) < 2 * m:
        raise ValueError("当前范围至少需要 2 × M 条记录，才能找到不与当前样本重叠的历史区间。")
    values = frame.close.to_numpy(dtype=float)

    def normalized(path):
        if not np.isfinite(path).all() or (path <= 0).any():
            return None
        path = path / path[0] - 1
        centered = path - path.mean()
        length = np.linalg.norm(centered)
        return centered / length if length > 1e-12 else None

    sample = normalized(values[-m:])
    if sample is None:
        raise ValueError("当前样本价格缺失、无效或走势完全横盘，无法计算相关性。")
    candidates = []
    for start in range(len(values) - 2 * m + 1):
        path = normalized(values[start:start + m])
        if path is not None:
            score = float(np.clip(np.dot(sample, path), -1, 1))
            if score > 0:
                candidates.append((score, start))
    chosen = []
    for score, start in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if all(abs(start - other) >= m for _, other in chosen):
            chosen.append((score, start))
            if len(chosen) == n:
                break
    return [SimilarPeriod(frame.date.iloc[start], frame.date.iloc[start + m - 1], score)
            for score, start in chosen]
