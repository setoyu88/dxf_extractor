"""寸法・テキスト寸法Pydanticモデル。"""
from __future__ import annotations

from enum import Enum
from typing import ClassVar

from pydantic import BaseModel

from dxf_extractor.models.shape import BoundingBox, OmitNoneMixin, Point2D


class DimensionType(str, Enum):
    """寸法種別。"""

    linear = "linear"
    radial = "radial"
    angular = "angular"
    diameter = "diameter"
    ordinate = "ordinate"


class DimensionDirection(str, Enum):
    """寸法方向。寸法線の向きで判定する。"""

    x = "x"
    y = "y"
    parallel = "parallel"


class Dimension(OmitNoneMixin):
    """記号寸法（DIMENSIONエンティティ）。"""

    id: str
    dim_type: DimensionType
    direction: DimensionDirection | None = None
    value: float | None = None
    text: str
    position: Point2D
    extension_point_1: Point2D | None = None
    extension_point_2: Point2D | None = None
    layer: str
    tolerance: "Tolerance | None" = None  # 循環参照回避のため文字列型ヒント
    # 帰属シート識別子（US2 / FR-204）。既定Noneで出力省略。
    sheet: str | None = None

    # 既存の任意フィールド（direction/value 等）は従来どおり null 出力。sheet のみ省略対象。
    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ("sheet",)


class TextDimension(BaseModel):
    """テキスト寸法（TEXT/MTEXTから正規表現で抽出）。"""

    id: str
    value: float
    text: str
    position: Point2D
    bounding_box: BoundingBox
    layer: str
    is_duplicate: bool = False


# 遅延インポートで循環参照を回避
from dxf_extractor.models.tolerance import Tolerance  # noqa: E402

Dimension.model_rebuild()
