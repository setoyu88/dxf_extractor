"""Rule10（部品番号紐づけ）カテゴリAの実装。"""
import math

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import BlockType, LogicalBlock
from dxf_extractor.models.dimension import TextDimension
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.shape import BoundingBox, Point2D
from dxf_extractor.models.table import Table

_PART_NO_LAYER_KEYWORDS = {"part_no", "PART_NO", "partno", "PARTNO", "text", "TEXT"}


def _is_part_number_layer(layer: str) -> bool:
    return any(kw.lower() == layer.lower() for kw in _PART_NO_LAYER_KEYWORDS)


def _is_integer_value(tdim: TextDimension) -> bool:
    return float(tdim.value) == int(tdim.value) and int(tdim.value) >= 1


def _is_part_number_candidate(tdim: TextDimension, style: str) -> bool:
    """部品番号候補かを判定する（US4 / FR-403）。

    integer_text（既定）: part_no レイヤの整数テキストのみ（現行挙動）。
    balloon / both: バルーン番号（多くは任意レイヤ・INSERT由来）に対応するため、
    レイヤ制約を外し整数テキストを広く候補化する。
    """
    if not (_is_integer_value(tdim) and not tdim.is_duplicate):
        return False
    if _is_part_number_layer(tdim.layer):
        return True
    return style in ("balloon", "both")


def _is_in_bbox(point: Point2D, bbox: BoundingBox, margin: float = 0.0) -> bool:
    return (
        bbox.min_x - margin <= point.x <= bbox.max_x + margin
        and bbox.min_y - margin <= point.y <= bbox.max_y + margin
    )


def _dist_to_center(point: Point2D, bbox: BoundingBox) -> float:
    cx = (bbox.min_x + bbox.max_x) / 2
    cy = (bbox.min_y + bbox.max_y) / 2
    return math.sqrt((point.x - cx) ** 2 + (point.y - cy) ** 2)


def _find_part_number_column(table: Table) -> int | None:
    """部品表の「番号」列インデックスを返す。"""
    _PART_NO_COLS = {"番号", "NO", "No", "no", "part no", "Part No"}
    if not table.rows:
        return None
    header = table.rows[0]
    for cell in header.cells:
        if any(kw in cell.text for kw in _PART_NO_COLS):
            return cell.col
    return None


class Rule10PartNumber(AssociatorBase):
    """Rule10: 部品番号紐づけ（カテゴリA）。"""

    RULE_ID = "10"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """部品番号識別・部品ビュー関連付け・部品表行関連付けを実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []
        delta = config.tolerances.delta
        style = config.profile.part_number_style
        part_views = [b for b in drawing.blocks if b.type == BlockType.part_view]

        part_number_tdims: list[TextDimension] = []

        for tdim in drawing.text_dimensions:
            if _is_part_number_candidate(tdim, style):
                part_number_tdims.append(tdim)
                # Rule 10-1: 部品番号テキストの識別
                results.append(
                    AssociationResult(
                        rule="10-1",
                        source_id=tdim.id,
                        target_ids=[f"part_number:{int(tdim.value)}"],
                        confidence=1.0,
                    )
                )

                # Rule 10-2: 部品番号と部品ビューの関連付け
                matched_blocks = [
                    b.id for b in part_views
                    if _is_in_bbox(tdim.position, b.bounding_box, margin=delta)
                ]
                if matched_blocks:
                    results.append(
                        AssociationResult(
                            rule="10-2",
                            source_id=tdim.id,
                            target_ids=matched_blocks,
                            confidence=1.0,
                        )
                    )
                elif part_views:
                    # 最近傍ブロックにフォールバック
                    nearest = min(part_views, key=lambda b: _dist_to_center(tdim.position, b.bounding_box))
                    results.append(
                        AssociationResult(
                            rule="10-2",
                            source_id=tdim.id,
                            target_ids=[nearest.id],
                            confidence=0.7,
                        )
                    )

                # Rule 10-3: 部品番号と部品表行の関連付け
                for table in drawing.tables:
                    no_col = _find_part_number_column(table)
                    if no_col is None:
                        continue
                    for row in table.rows[1:]:  # ヘッダー行をスキップ
                        for cell in row.cells:
                            if cell.col == no_col:
                                try:
                                    if int(float(cell.text)) == int(tdim.value):
                                        results.append(
                                            AssociationResult(
                                                rule="10-3",
                                                source_id=tdim.id,
                                                target_ids=[f"{table.id}:row:{row.index}"],
                                                confidence=1.0,
                                            )
                                        )
                                except (ValueError, TypeError):
                                    pass

        return results
