"""注記Pydanticモデル。"""
from typing import ClassVar

from dxf_extractor.models.shape import BoundingBox, OmitNoneMixin, Point2D


class Note(OmitNoneMixin):
    """注記テキスト（TEXT/MTEXT）。"""

    id: str
    text: str
    position: Point2D
    bounding_box: BoundingBox
    layer: str
    entity_type: str
    # 帰属シート識別子（US2 / FR-204）。既定Noneで出力省略。
    sheet: str | None = None

    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ("sheet",)
