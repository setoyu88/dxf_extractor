"""論理ブロックPydanticモデル。"""
from enum import Enum

from pydantic import BaseModel

from dxf_extractor.models.shape import BoundingBox, Point2D


class BlockType(str, Enum):
    """論理ブロック種別。"""

    part_view = "part_view"
    sub_view = "sub_view"
    table = "table"
    frame = "frame"
    notes = "notes"


class LogicalBlock(BaseModel):
    """論理ブロック。DBSCANでクラスタリングされた図面要素の集合。"""

    id: str
    type: BlockType
    name: str | None = None
    position: Point2D
    bounding_box: BoundingBox
    shape_ids: list[str] = []
    dimension_ids: list[str] = []
    note_ids: list[str] = []
    llm_labeled: bool = False
