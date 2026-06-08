"""関連付け結果・体系化図面Pydanticモデル。"""
from pydantic import BaseModel, field_validator, model_validator

from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.dimension import Dimension, TextDimension
from dxf_extractor.models.drawing import DXFDrawing, Metadata
from dxf_extractor.models.layer import Layer
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import Shape
from dxf_extractor.models.table import Table
from dxf_extractor.models.tolerance import Tolerance


class AssociationResult(BaseModel):
    """1つの関連付け結果。"""

    rule: str
    source_id: str
    target_ids: list[str]
    confidence: float
    extracted_value: str | None = None
    llm_augmented: bool = False
    llm_error: bool = False

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        """confidenceは0.0〜1.0の範囲でなければならない。"""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence は 0.0〜1.0 の範囲でなければなりません。指定値: {v}")
        return v

    @field_validator("rule")
    @classmethod
    def rule_not_empty(cls, v: str) -> str:
        """ruleは空文字列禁止。"""
        if not v:
            raise ValueError("rule は空文字列にできません")
        return v

    @field_validator("source_id")
    @classmethod
    def source_id_not_empty(cls, v: str) -> str:
        """source_idは空文字列禁止。"""
        if not v:
            raise ValueError("source_id は空文字列にできません")
        return v

    @model_validator(mode="after")
    def llm_error_implies_not_augmented(self) -> "AssociationResult":
        """llm_error=True の場合、llm_augmented は必ず False でなければならない。"""
        if self.llm_error and self.llm_augmented:
            raise ValueError("llm_error=True の場合、llm_augmented は False でなければなりません")
        return self


class StructuredDrawing(BaseModel):
    """体系化済み図面全体。入力JSONの全フィールドを保持した上に associations を追加する。"""

    metadata: Metadata
    blocks: list[LogicalBlock] = []
    shapes: list[Shape] = []
    dimensions: list[Dimension] = []
    text_dimensions: list[TextDimension] = []
    tolerances: list[Tolerance] = []
    tables: list[Table] = []
    notes: list[Note] = []
    layers: list[Layer] = []
    associations: list[AssociationResult] = []

    @classmethod
    def from_drawing(cls, drawing: DXFDrawing) -> "StructuredDrawing":
        """DXFDrawingから StructuredDrawing を生成する。

        Args:
            drawing: 入力DXF図面。

        Returns:
            StructuredDrawing: 体系化済み図面（associationsは空リスト）。
        """
        return cls(
            metadata=drawing.metadata,
            blocks=drawing.blocks,
            shapes=drawing.shapes,
            dimensions=drawing.dimensions,
            text_dimensions=drawing.text_dimensions,
            tolerances=drawing.tolerances,
            tables=drawing.tables,
            notes=drawing.notes,
            layers=drawing.layers,
        )
