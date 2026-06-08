"""テキスト寸法と記号寸法の重複検出・is_duplicate フラグ付与（FR-006）。"""
import math

from dxf_extractor.models.dimension import Dimension, TextDimension
from dxf_extractor.models.shape import Point2D

_DEFAULT_THRESHOLD = 5.0


def resolve_duplicates(
    text_dimensions: list[TextDimension],
    dimensions: list[Dimension],
    threshold: float = _DEFAULT_THRESHOLD,
) -> list[TextDimension]:
    """テキスト寸法と記号寸法の重複を検出し、is_duplicate フラグを付与する（FR-006）。

    同一値かつ指定した閾値内に位置する場合に重複と判定する。

    Args:
        text_dimensions: テキスト寸法リスト。
        dimensions: 記号寸法リスト。
        threshold: 重複判定の距離閾値（DXFユニット）。

    Returns:
        list[TextDimension]: is_duplicate フラグが更新されたテキスト寸法リスト。
    """
    result: list[TextDimension] = []
    for tdim in text_dimensions:
        is_dup = _check_duplicate(tdim, dimensions, threshold)
        if is_dup != tdim.is_duplicate:
            result.append(tdim.model_copy(update={"is_duplicate": is_dup}))
        else:
            result.append(tdim)
    return result


def _check_duplicate(
    tdim: TextDimension,
    dimensions: list[Dimension],
    threshold: float,
) -> bool:
    """テキスト寸法が記号寸法と重複するかどうかを判定する。

    Args:
        tdim: 判定対象のテキスト寸法。
        dimensions: 比較対象の記号寸法リスト。
        threshold: 距離閾値（DXFユニット）。

    Returns:
        bool: 重複している場合True。
    """
    for dim in dimensions:
        if dim.value is None:
            continue
        if abs(dim.value - tdim.value) > 1e-6:
            continue
        if _distance(tdim.position, dim.position) <= threshold:
            return True
    return False


def _distance(p1: Point2D, p2: Point2D) -> float:
    """2点間のユークリッド距離を計算する。

    Args:
        p1: 点1。
        p2: 点2。

    Returns:
        float: 距離（DXFユニット）。
    """
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)
