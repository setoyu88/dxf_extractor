"""Rule1（寸法↔形状マッチング）カテゴリAの実装。"""
import math

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.dimension import Dimension, DimensionType
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.shape import (
    BoundingBox,
    CircleGeometry,
    LineGeometry,
    Point2D,
    PolylineGeometry,
    Shape,
)


def _dist(p1: Point2D, p2: Point2D) -> float:
    return math.sqrt((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2)


def _is_in_bbox(point: Point2D, bbox: BoundingBox) -> bool:
    return bbox.min_x <= point.x <= bbox.max_x and bbox.min_y <= point.y <= bbox.max_y


def _shape_endpoints(shape: Shape) -> list[Point2D]:
    """形状の端点リストを返す。"""
    geom = shape.geometry
    if isinstance(geom, LineGeometry):
        return [geom.start, geom.end]
    if isinstance(geom, PolylineGeometry):
        return list(geom.vertices)
    return []


def _matches_endpoint(shape: Shape, point: Point2D, delta: float) -> bool:
    """形状の端点がpoint から delta以内にあるかどうかを判定する。"""
    for ep in _shape_endpoints(shape):
        if _dist(ep, point) <= delta:
            return True
    return False


class Rule1DimensionShape(AssociatorBase):
    """Rule1: 寸法↔形状マッチング（カテゴリA）。"""

    RULE_ID = "1"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """線形寸法端点マッチング・径寸法円マッチング・ブロック帰属確認を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []
        delta = config.tolerances.delta

        for dim in drawing.dimensions:
            # Rule 1-1: 線形寸法の端点マッチング
            if (
                dim.dim_type == DimensionType.linear
                and dim.extension_point_1 is not None
                and dim.extension_point_2 is not None
            ):
                matched = [
                    s.id
                    for s in drawing.shapes
                    if _matches_endpoint(s, dim.extension_point_1, delta)
                    or _matches_endpoint(s, dim.extension_point_2, delta)
                ]
                if matched:
                    results.append(
                        AssociationResult(
                            rule="1-1",
                            source_id=dim.id,
                            target_ids=matched,
                            confidence=1.0,
                        )
                    )

            # Rule 1-2: 径寸法・直径寸法と円形状のマッチング
            if dim.dim_type in (DimensionType.diameter, DimensionType.radial):
                matched_circles = []
                for shape in drawing.shapes:
                    if isinstance(shape.geometry, CircleGeometry):
                        center = shape.geometry.center
                        radius = shape.geometry.radius
                        if _dist(dim.position, center) <= radius:
                            matched_circles.append(shape.id)
                if matched_circles:
                    results.append(
                        AssociationResult(
                            rule="1-2",
                            source_id=dim.id,
                            target_ids=matched_circles,
                            confidence=1.0,
                        )
                    )

            # Rule 1-3: 寸法のブロック帰属確認
            ep1 = dim.extension_point_1
            ep2 = dim.extension_point_2
            for block in drawing.blocks:
                if (ep1 and _is_in_bbox(ep1, block.bounding_box)) or (
                    ep2 and _is_in_bbox(ep2, block.bounding_box)
                ):
                    results.append(
                        AssociationResult(
                            rule="1-3",
                            source_id=dim.id,
                            target_ids=[block.id],
                            confidence=1.0,
                        )
                    )

        return results
