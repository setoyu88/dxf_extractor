"""Rule5（注記↔形状対応）カテゴリA/Bの実装。"""
import math

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.associators.llm_helper import try_llm_augment
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import BoundingBox, OtherGeometry, Point2D, Shape

_ANNOTATION_LAYER_KEYWORDS = {"annotation", "ANNOTATION", "text", "TEXT", "note", "NOTE"}
_CROSS_LAYER_KEYWORDS = {"cross", "CROSS", "section", "SECTION"}
_TABLE_LAYER_KEYWORDS = {"table", "TABLE"}


def _classify_layer(layer: str) -> str | None:
    """レイヤー名から大分類を返す。"""
    layer_lower = layer.lower()
    if any(kw.lower() in layer_lower for kw in _ANNOTATION_LAYER_KEYWORDS):
        return "annotation"
    if any(kw.lower() in layer_lower for kw in _CROSS_LAYER_KEYWORDS):
        return "cross"
    if any(kw.lower() in layer_lower for kw in _TABLE_LAYER_KEYWORDS):
        return "table"
    return None


def _dist_to_bbox(point: Point2D, bbox: BoundingBox) -> float:
    """点からバウンディングボックスへの最短距離。"""
    dx = max(bbox.min_x - point.x, 0, point.x - bbox.max_x)
    dy = max(bbox.min_y - point.y, 0, point.y - bbox.max_y)
    return math.sqrt(dx * dx + dy * dy)


def _is_leader(shape: Shape) -> bool:
    return isinstance(shape.geometry, OtherGeometry) and shape.geometry.entity_type == "LEADER"


class Rule5NoteShape(AssociatorBase):
    """Rule5: 注記↔形状対応（カテゴリA）。"""

    RULE_ID = "5"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """レイヤー大分類・LEADER指示線・近接テキストと形状対応を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []
        d_threshold = config.tolerances.d_threshold

        for note in drawing.notes:
            # Rule 5-1: レイヤーによる大分類
            category = _classify_layer(note.layer)
            if category:
                results.append(
                    AssociationResult(
                        rule="5-1",
                        source_id=note.id,
                        target_ids=[f"category:{category}"],
                        confidence=1.0,
                    )
                )

            # Rule 5-2: LEADER（引き出し線）による注記と形状の対応
            leader_shapes = [s for s in drawing.shapes if _is_leader(s)]
            for leader in leader_shapes:
                if _dist_to_bbox(note.position, leader.bounding_box) <= d_threshold:
                    results.append(
                        AssociationResult(
                            rule="5-2",
                            source_id=note.id,
                            target_ids=[leader.id],
                            confidence=1.0,
                        )
                    )

            # Rule 5-3: 近接テキストと形状の対応（カテゴリA/B）
            non_leader_shapes = [s for s in drawing.shapes if not _is_leader(s)]
            nearby = [
                s for s in non_leader_shapes
                if _dist_to_bbox(note.position, s.bounding_box) <= d_threshold
            ]
            if nearby:
                # 最近傍の形状を優先
                closest = min(nearby, key=lambda s: _dist_to_bbox(note.position, s.bounding_box))
                if llm_config is not None:
                    prompt = f"注記 '{note.text}' が関連する形状を判定してください。候補: {[s.id for s in nearby]}"
                    result = try_llm_augment(
                        rule_id="5-3",
                        source_id=note.id,
                        prompt=prompt,
                        llm_config=llm_config,
                        fallback_target_ids=[closest.id],
                    )
                    results.append(result)
                else:
                    results.append(
                        AssociationResult(
                            rule="5-3",
                            source_id=note.id,
                            target_ids=[closest.id],
                            confidence=1.0,
                        )
                    )

        return results
