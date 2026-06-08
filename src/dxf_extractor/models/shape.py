"""形状・共通型Pydanticモデル。"""
from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import BaseModel, field_validator, model_serializer


class OmitNoneMixin(BaseModel):
    """指定した任意フィールドが ``None`` のときのみ出力から省略する基底クラス。

    本機能（汎用化拡張）で追加した任意フィールド（``sheet`` 等）を、既定値（``None``）の
    ときにJSON出力へ出さないようにする。``_OMIT_WHEN_NONE`` に挙げたキーだけが対象で、
    既存フィールド（``None`` を ``null`` として出力する従来挙動）には一切影響しない
    （後方互換／ゴールデン不変。FR-001 / INV-2 / C-OUT-1）。
    """

    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _omit_none(self, handler: Any) -> Any:
        """``_OMIT_WHEN_NONE`` のキーが ``None`` の場合のみ出力から取り除く。"""
        data = handler(self)
        for key in type(self)._OMIT_WHEN_NONE:
            if isinstance(data, dict) and data.get(key) is None:
                data.pop(key, None)
        return data


class Point2D(BaseModel):
    """2D座標点。"""

    x: float
    y: float


class BoundingBox(BaseModel):
    """バウンディングボックス（包含領域）。"""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @field_validator("max_x")
    @classmethod
    def max_x_gte_min_x(cls, v: float, info: object) -> float:
        """max_x >= min_x を検証する。"""
        data = info.data  # type: ignore[attr-defined]
        if "min_x" in data and v < data["min_x"]:
            raise ValueError(f"max_x ({v}) は min_x ({data['min_x']}) 以上でなければなりません")
        return v

    @field_validator("max_y")
    @classmethod
    def max_y_gte_min_y(cls, v: float, info: object) -> float:
        """max_y >= min_y を検証する。"""
        data = info.data  # type: ignore[attr-defined]
        if "min_y" in data and v < data["min_y"]:
            raise ValueError(f"max_y ({v}) は min_y ({data['min_y']}) 以上でなければなりません")
        return v


class LineGeometry(BaseModel):
    """線分ジオメトリ。"""

    type: Literal["LINE"] = "LINE"
    start: Point2D
    end: Point2D


class ArcGeometry(BaseModel):
    """円弧ジオメトリ。"""

    type: Literal["ARC"] = "ARC"
    center: Point2D
    radius: float
    start_angle: float
    end_angle: float


class CircleGeometry(BaseModel):
    """円ジオメトリ。"""

    type: Literal["CIRCLE"] = "CIRCLE"
    center: Point2D
    radius: float


class PolylineGeometry(BaseModel):
    """ポリラインジオメトリ。"""

    type: Literal["POLYLINE"] = "POLYLINE"
    vertices: list[Point2D]
    is_closed: bool


class OtherGeometry(OmitNoneMixin):
    """サポート対象外エンティティを記録するジオメトリ。"""

    type: Literal["OTHER"] = "OTHER"
    entity_type: str
    raw_attributes: dict[str, str]
    # INSERT展開で生成された要素の由来ブロック名（US2 / FR-205）。既定Noneで出力省略。
    source_block: str | None = None

    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ("source_block",)


GeometryUnion = Annotated[
    Union[LineGeometry, ArcGeometry, CircleGeometry, PolylineGeometry, OtherGeometry],
    "discriminated union by type field",
]


class Shape(OmitNoneMixin):
    """形状エンティティ。"""

    id: str
    layer: str
    bounding_box: BoundingBox
    geometry: LineGeometry | ArcGeometry | CircleGeometry | PolylineGeometry | OtherGeometry
    # 帰属シート識別子（US2 / FR-204）。既定Noneで出力省略。
    sheet: str | None = None

    _OMIT_WHEN_NONE: ClassVar[tuple[str, ...]] = ("sheet",)
