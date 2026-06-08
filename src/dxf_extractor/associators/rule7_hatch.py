"""Rule7（ハッチング関連付け）カテゴリA/Bの実装。"""
from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.associators.llm_helper import try_llm_augment
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.shape import BoundingBox, OtherGeometry, PolylineGeometry, CircleGeometry, Shape


def _is_hatch(shape: Shape) -> bool:
    return isinstance(shape.geometry, OtherGeometry) and shape.geometry.entity_type == "HATCH"


def _is_leader(shape: Shape) -> bool:
    return isinstance(shape.geometry, OtherGeometry) and shape.geometry.entity_type == "LEADER"


def _bbox_contains_bbox(outer: BoundingBox, inner: BoundingBox) -> bool:
    return (
        outer.min_x <= inner.min_x
        and outer.min_y <= inner.min_y
        and outer.max_x >= inner.max_x
        and outer.max_y >= inner.max_y
    )


def _is_closed_shape(shape: Shape) -> bool:
    geom = shape.geometry
    if isinstance(geom, PolylineGeometry):
        return geom.is_closed
    if isinstance(geom, CircleGeometry):
        return True
    return False


def _find_block_for_shape(shape: Shape, blocks: list[LogicalBlock]) -> LogicalBlock | None:
    for block in blocks:
        if shape.id in block.shape_ids:
            return block
    # bounding_box で判定
    for block in blocks:
        bb = block.bounding_box
        if bb.min_x <= shape.bounding_box.min_x and bb.max_x >= shape.bounding_box.max_x:
            if bb.min_y <= shape.bounding_box.min_y and bb.max_y >= shape.bounding_box.max_y:
                return block
    return None


class Rule7Hatch(AssociatorBase):
    """Rule7: ハッチング関連付け（カテゴリA）。"""

    RULE_ID = "7"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """ハッチング境界形状特定・LEADER関連付け・断面表示対応を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []
        hatches = [s for s in drawing.shapes if _is_hatch(s)]
        non_hatches = [s for s in drawing.shapes if not _is_hatch(s)]

        for hatch in hatches:
            hbb = hatch.bounding_box

            # Rule 7-1: ハッチングの境界形状特定
            boundary_ids = [
                s.id for s in non_hatches
                if _is_closed_shape(s) and _bbox_contains_bbox(hbb, s.bounding_box)
            ]
            if boundary_ids:
                results.append(
                    AssociationResult(
                        rule="7-1",
                        source_id=hatch.id,
                        target_ids=boundary_ids,
                        confidence=1.0,
                    )
                )
            else:
                # ハッチング自体の結果として空でない target を保証
                results.append(
                    AssociationResult(
                        rule="7-1",
                        source_id=hatch.id,
                        target_ids=["no_boundary"],
                        confidence=0.5,
                    )
                )

            # Rule 7-2: ハッチングとLEADERの関連付け（カテゴリA/B）
            hatch_block = _find_block_for_shape(hatch, drawing.blocks)
            if hatch_block:
                leader_ids = [
                    s.id for s in non_hatches
                    if _is_leader(s) and s.id in hatch_block.shape_ids
                ]
                if leader_ids and llm_config is not None:
                    prompt = f"ハッチング {hatch.id} に対応するLEADER引き出し線を特定してください。候補: {leader_ids}"
                    result = try_llm_augment(
                        rule_id="7-2",
                        source_id=hatch.id,
                        prompt=prompt,
                        llm_config=llm_config,
                        fallback_target_ids=leader_ids,
                    )
                    results.append(result)
                elif leader_ids:
                    results.append(
                        AssociationResult(
                            rule="7-2",
                            source_id=hatch.id,
                            target_ids=leader_ids,
                            confidence=1.0,
                        )
                    )

            # Rule 7-3: ハッチングと断面表示の対応付け
            if "cross" in hatch.layer.lower():
                results.append(
                    AssociationResult(
                        rule="7-3",
                        source_id=hatch.id,
                        target_ids=["cross_section"],
                        confidence=1.0,
                    )
                )

        return results
