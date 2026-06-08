"""Rule6（視図間投影関係）カテゴリAの実装。"""
from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import BlockType, LogicalBlock
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.shape import BoundingBox


def _x_ranges_overlap(a: BoundingBox, b: BoundingBox) -> bool:
    return a.min_x <= b.max_x and a.max_x >= b.min_x


def _y_ranges_overlap(a: BoundingBox, b: BoundingBox) -> bool:
    return a.min_y <= b.max_y and a.max_y >= b.min_y


def _part_view_blocks(blocks: list[LogicalBlock]) -> list[LogicalBlock]:
    return [b for b in blocks if b.type == BlockType.part_view]


class Rule6ViewProjection(AssociatorBase):
    """Rule6: 視図間投影関係（カテゴリA）。"""

    RULE_ID = "6"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """座標軸投影対応・共通寸法による視図同定を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []
        part_views = _part_view_blocks(drawing.blocks)

        if len(part_views) < 2:
            return results

        # Rule 6-1: 座標軸による投影対応
        paired: set[frozenset[str]] = set()
        for i, block_a in enumerate(part_views):
            for block_b in part_views[i + 1 :]:
                pair = frozenset([block_a.id, block_b.id])
                if pair in paired:
                    continue

                ba = block_a.bounding_box
                bb = block_b.bounding_box

                # x座標範囲が重なり、y方向に離れている（正面図と上面図の関係）
                if _x_ranges_overlap(ba, bb) and not _y_ranges_overlap(ba, bb):
                    results.append(
                        AssociationResult(
                            rule="6-1",
                            source_id=block_a.id,
                            target_ids=[block_b.id],
                            confidence=1.0,
                        )
                    )
                    paired.add(pair)

                # y座標範囲が重なり、x方向に離れている（正面図と側面図の関係）
                elif _y_ranges_overlap(ba, bb) and not _x_ranges_overlap(ba, bb):
                    results.append(
                        AssociationResult(
                            rule="6-1",
                            source_id=block_a.id,
                            target_ids=[block_b.id],
                            confidence=1.0,
                        )
                    )
                    paired.add(pair)

        # Rule 6-2: 共通寸法による視図の同定
        block_dim_map: dict[str, set[str]] = {b.id: set(b.dimension_ids) for b in part_views}
        for i, block_a in enumerate(part_views):
            for block_b in part_views[i + 1 :]:
                common_dims = block_dim_map[block_a.id] & block_dim_map[block_b.id]
                if common_dims:
                    results.append(
                        AssociationResult(
                            rule="6-2",
                            source_id=block_a.id,
                            target_ids=[block_b.id],
                            confidence=1.0,
                        )
                    )

        return results
