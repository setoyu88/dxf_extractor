"""DXFDrawingトップレベルモデルとMetadataモデル。"""
from typing import ClassVar, Literal

from pydantic import BaseModel, field_validator

from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.dimension import Dimension, TextDimension
from dxf_extractor.models.layer import Layer
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import OmitNoneMixin, Shape
from dxf_extractor.models.table import Table
from dxf_extractor.models.tolerance import Tolerance


class ScaleContext(BaseModel):
    """しきい値自動スケールの推定文脈（US3 / FR-304）。

    Attributes:
        unit: 採用した図面単位（$INSUNITS 由来 or 推定）。
        factor: 関連付け・クラスタリングのしきい値へ乗ずる係数（既定1.0）。
        source: 係数の推定根拠（insunits / bbox / default）。
    """

    unit: str
    factor: float
    source: Literal["insunits", "bbox", "default"]


class Metadata(OmitNoneMixin):
    """図面メタ情報。"""

    title: str | None = None
    drawing_number: str | None = None
    revision: str | None = None
    scale: str | None = None
    created_by: str | None = None
    designed_by: str | None = None
    checked_by: str | None = None
    approved_by: str | None = None
    material: str | None = None
    dxf_version: str
    # 自動スケール有効時のみ付与される推定文脈（US3 / FR-304）。既定Noneで出力省略。
    scale_context: ScaleContext | None = None

    # 既存の任意フィールド（title 等）は従来どおり null 出力。scale_context のみ省略対象。
    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ("scale_context",)

    @field_validator("dxf_version")
    @classmethod
    def dxf_version_not_empty(cls, v: str) -> str:
        """dxf_versionは空文字列禁止。"""
        if not v:
            raise ValueError("dxf_versionは空文字列にできません")
        return v


class DXFDrawing(BaseModel):
    """DXF図面の全抽出結果（トップレベル出力）。"""

    metadata: Metadata
    blocks: list[LogicalBlock] = []
    shapes: list[Shape] = []
    dimensions: list[Dimension] = []
    text_dimensions: list[TextDimension] = []
    tolerances: list[Tolerance] = []
    tables: list[Table] = []
    notes: list[Note] = []
    layers: list[Layer] = []

    @field_validator("shapes", "dimensions", "text_dimensions", "tolerances", "tables", "notes", "blocks", mode="after")
    @classmethod
    def check_unique_ids(cls, v: list, info: object) -> list:
        """全IDが一意であることを検証する（SC-005）。"""
        ids = [item.id for item in v if hasattr(item, "id")]
        if len(ids) != len(set(ids)):
            field = getattr(info, "field_name", "field")
            raise ValueError(f"{field} 内に重複するIDが存在します")
        return v
