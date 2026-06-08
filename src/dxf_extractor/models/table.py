"""表Pydanticモデル。"""
from typing import ClassVar

from pydantic import BaseModel

from dxf_extractor.models.shape import BoundingBox, OmitNoneMixin, Point2D


class TableCell(BaseModel):
    """表のセル。"""

    row: int
    col: int
    text: str
    position: Point2D | None = None


class TableRow(BaseModel):
    """表の行。"""

    index: int
    cells: list[TableCell]


class Table(OmitNoneMixin):
    """表（部品表・公差表・注記表など）。"""

    id: str
    rows: list[TableRow]
    position: Point2D
    bounding_box: BoundingBox
    layer: str
    # 帰属シート識別子（US2 / FR-204）。既定Noneで出力省略。
    sheet: str | None = None

    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ("sheet",)
