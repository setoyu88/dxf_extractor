"""DIMENSIONエンティティ抽出（記号寸法）。"""
import math
from typing import Iterable

from dxf_extractor.parsers.entity_source import sheet_of
from dxf_extractor.utils import sanitize_surrogates
from dxf_extractor.models.dimension import Dimension, DimensionDirection, DimensionType
from dxf_extractor.models.shape import Point2D

_ANGLE_TOLERANCE_DEG = 0.5

_DIM_TYPE_MAP = {
    0: DimensionType.linear,
    1: DimensionType.angular,
    2: DimensionType.diameter,
    3: DimensionType.radial,
    4: DimensionType.angular,
    5: DimensionType.angular,
    6: DimensionType.ordinate,
}


def _determine_direction(dxf: object, dim_type_code: int, ext1: Point2D | None, ext2: Point2D | None) -> DimensionDirection | None:
    """寸法線の向きからx/y/parallelを判定する。

    Args:
        dxf: ezdxf DXFネームスペース。
        dim_type_code: DXF dimtype下位4ビット。
        ext1: 引出点1（defpoint2）。
        ext2: 引出点2（defpoint3）。

    Returns:
        DimensionDirection | None: 方向。線形以外の寸法種別はNone。
    """
    if dim_type_code == 0:
        # 回転線形寸法: dxf.angle が寸法線の水平からの角度
        angle = float(dxf.get("angle", 0.0))  # type: ignore[attr-defined]
        normalized = angle % 180.0
        if normalized < _ANGLE_TOLERANCE_DEG or normalized > 180.0 - _ANGLE_TOLERANCE_DEG:
            return DimensionDirection.x
        if abs(normalized - 90.0) < _ANGLE_TOLERANCE_DEG:
            return DimensionDirection.y
        return DimensionDirection.parallel

    if dim_type_code == 1:
        # 沿線（aligned）寸法: defpoint2→defpoint3 ベクトルで判定
        if ext1 is None or ext2 is None:
            return None
        dx = abs(ext2.x - ext1.x)
        dy = abs(ext2.y - ext1.y)
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        angle_deg = math.degrees(math.atan2(dy, dx)) % 180.0
        if angle_deg < _ANGLE_TOLERANCE_DEG or angle_deg > 180.0 - _ANGLE_TOLERANCE_DEG:
            return DimensionDirection.x
        if abs(angle_deg - 90.0) < _ANGLE_TOLERANCE_DEG:
            return DimensionDirection.y
        return DimensionDirection.parallel

    return None


def extract_dimensions(entities: Iterable) -> list[Dimension]:
    """エンティティ列からDIMENSIONエンティティを抽出する（FR-006・FR-021）。

    Args:
        entities: 反復対象エンティティ列（entity_source 供給または モデルスペース）。

    Returns:
        list[Dimension]: 抽出した記号寸法リスト。
    """
    dimensions: list[Dimension] = []
    counter = 1

    for entity in entities:
        if entity.dxftype() != "DIMENSION":
            continue
        try:
            dim = _extract_dimension(entity, counter)
            if dim is not None:
                dim.sheet = sheet_of(entity)
                dimensions.append(dim)
                counter += 1
        except Exception:
            counter += 1

    return dimensions


def _extract_dimension(entity: object, counter: int) -> Dimension | None:
    """DIMENSIONエンティティからDimensionモデルを生成する。

    Args:
        entity: ezdxf DIMENSIONエンティティ。
        counter: ID採番用カウンター。

    Returns:
        Dimension | None: 生成したDimensionオブジェクト。失敗時はNone。
    """
    dxf = entity.dxf  # type: ignore[attr-defined]
    layer = sanitize_surrogates(dxf.get("layer", "0"))

    dim_type_code = dxf.get("dimtype", 0) & 0x0F
    dim_type = _DIM_TYPE_MAP.get(dim_type_code, DimensionType.linear)

    text_midpoint = dxf.get("text_midpoint", None)
    if text_midpoint is None:
        return None
    position = Point2D(x=float(text_midpoint.x), y=float(text_midpoint.y))

    raw_text: str = dxf.get("text", "") or ""
    value: float | None = None
    try:
        clean = raw_text.replace("<>", "").strip()
        if clean:
            value = float(clean)
        else:
            meas = dxf.get("actual_measurement", None)
            if meas is not None:
                value = float(meas)
    except (ValueError, TypeError):
        pass

    ext1: Point2D | None = None
    ext2: Point2D | None = None
    try:
        p = dxf.get("defpoint2", None)
        if p:
            ext1 = Point2D(x=float(p.x), y=float(p.y))
        p = dxf.get("defpoint3", None)
        if p:
            ext2 = Point2D(x=float(p.x), y=float(p.y))
    except Exception:
        pass

    direction = _determine_direction(dxf, dim_type_code, ext1, ext2)

    return Dimension(
        id=f"dim_{counter:03d}",
        dim_type=dim_type,
        direction=direction,
        value=value,
        text=raw_text or (str(value) if value is not None else ""),
        position=position,
        extension_point_1=ext1,
        extension_point_2=ext2,
        layer=layer,
    )
