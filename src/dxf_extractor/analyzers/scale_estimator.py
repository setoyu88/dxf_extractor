"""図面スケールの推定（US3 / FR-301〜304）。

関連付け・クラスタリングのしきい値は mm・一般的図面サイズを前提とした絶対値である。
本モジュールは図面の実座標スケールに応じた係数 `factor` を推定し、しきい値へ乗ずることで
単位・尺度への依存を緩和する。

係数は図面の外接範囲（実座標の広がり）を基準サイズで正規化して求める。これにより、
同一形状の mm版・inch版・10倍スケール版のいずれでも、距離としきい値が同じ比率でスケールし、
構造化結果が等価になる（SC-004）。`$INSUNITS` は採用単位ラベルと推定根拠の記録に用いる。

既定（`auto_scale=False`）では係数を 1.0 とし、現行の絶対値しきい値を維持する（FR-303 / 後方互換）。
"""
import logging

from ezdxf.document import Drawing

from dxf_extractor.config import ScaleConfig
from dxf_extractor.models.drawing import ScaleContext
from dxf_extractor.models.shape import Shape

logger = logging.getLogger(__name__)

# 係数正規化の基準サイズ（図面の代表寸法。係数=外接範囲/基準サイズ）。
_REFERENCE_SIZE = 100.0

# $INSUNITS コード → 単位名（主要なもの）。
_INSUNITS_MAP = {
    1: "inch",
    2: "feet",
    4: "mm",
    5: "cm",
    6: "m",
}


def estimate_scale(doc: Drawing, shapes: list[Shape], config: ScaleConfig | None = None) -> ScaleContext:
    """図面からスケール文脈を推定する。

    Args:
        doc: ezdxf Drawing（`$INSUNITS` 参照用）。
        shapes: 抽出済み形状（外接範囲の算出用）。
        config: スケール設定。None または `auto_scale=False` のとき係数1.0。

    Returns:
        ScaleContext: 採用単位・係数・推定根拠。
    """
    if config is None:
        config = ScaleConfig()

    unit = _read_unit(doc) or config.base_unit

    if not config.auto_scale:
        return ScaleContext(unit=unit, factor=1.0, source="default")

    extent = _overall_extent(shapes)
    if extent <= 0:
        logger.warning("[WARN] 形状の外接範囲を算出できないため、スケール係数を1.0にフォールバックします。")
        return ScaleContext(unit=unit, factor=1.0, source="default")

    reference = config.reference_size if config.reference_size and config.reference_size > 0 else _REFERENCE_SIZE
    factor = extent / reference
    source = "insunits" if _read_unit(doc) is not None else "bbox"
    return ScaleContext(unit=unit, factor=factor, source=source)


def _read_unit(doc: Drawing) -> str | None:
    """ヘッダ `$INSUNITS` から単位名を返す（取得不能・未設定は None）。"""
    try:
        code = int(doc.header.get("$INSUNITS", 0))
    except Exception:
        return None
    return _INSUNITS_MAP.get(code)


def _overall_extent(shapes: list[Shape]) -> float:
    """全形状の外接範囲の代表寸法（幅・高さの大きい方）を返す。"""
    xs_min: list[float] = []
    ys_min: list[float] = []
    xs_max: list[float] = []
    ys_max: list[float] = []
    for s in shapes:
        bb = s.bounding_box
        # 面積ゼロ（座標なし）の形状は無視する
        if bb.max_x == bb.min_x and bb.max_y == bb.min_y:
            continue
        xs_min.append(bb.min_x)
        ys_min.append(bb.min_y)
        xs_max.append(bb.max_x)
        ys_max.append(bb.max_y)
    if not xs_min:
        return 0.0
    return max(max(xs_max) - min(xs_min), max(ys_max) - min(ys_min))
