"""Rule2（テキスト寸法分類）カテゴリAの実装。"""
from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.shape import BoundingBox, Point2D

_DIM_LAYER_KEYWORDS = {"dim", "dimension", "scale", "寸法"}
_TABLE_LAYER_KEYWORDS = {"table", "テーブル", "部品"}


def _is_dimension_layer(layer: str) -> bool:
    layer_lower = layer.lower()
    return any(kw in layer_lower for kw in _DIM_LAYER_KEYWORDS)


def _is_table_layer(layer: str) -> bool:
    layer_lower = layer.lower()
    return any(kw in layer_lower for kw in _TABLE_LAYER_KEYWORDS)


def _is_in_bbox(point: Point2D, bbox: BoundingBox) -> bool:
    return bbox.min_x <= point.x <= bbox.max_x and bbox.min_y <= point.y <= bbox.max_y


class Rule2TdimClassifier(AssociatorBase):
    """Rule2: テキスト寸法分類（カテゴリA）。"""

    RULE_ID = "2"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """レイヤーによるtdim分類・テーブル番号との位置マッチングを実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []

        for tdim in drawing.text_dimensions:
            # Rule 2-1: レイヤーによる分類
            if _is_dimension_layer(tdim.layer):
                results.append(
                    AssociationResult(
                        rule="2-1",
                        source_id=tdim.id,
                        target_ids=["寸法線"],
                        confidence=1.0,
                    )
                )
            elif _is_table_layer(tdim.layer):
                results.append(
                    AssociationResult(
                        rule="2-1",
                        source_id=tdim.id,
                        target_ids=["テーブル番号"],
                        confidence=1.0,
                    )
                )

            # Rule 2-2: テーブル番号との位置マッチング
            for table in drawing.tables:
                if _is_in_bbox(tdim.position, table.bounding_box):
                    results.append(
                        AssociationResult(
                            rule="2-2",
                            source_id=tdim.id,
                            target_ids=[table.id],
                            confidence=1.0,
                        )
                    )
                    break

        return results
