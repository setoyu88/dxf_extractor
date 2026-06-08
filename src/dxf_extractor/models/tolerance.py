"""公差Pydanticモデル。"""
from enum import Enum

from pydantic import BaseModel

from dxf_extractor.models.shape import Point2D


class ToleranceType(str, Enum):
    """公差種別。"""

    symmetric = "symmetric"
    bilateral = "bilateral"
    grade = "grade"


class Tolerance(BaseModel):
    """公差情報。"""

    id: str
    tol_type: ToleranceType
    text: str
    upper: float | None = None
    lower: float | None = None
    grade: str | None = None
    fit: str | None = None
    position: Point2D
    layer: str
