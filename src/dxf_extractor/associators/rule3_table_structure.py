"""Rule3（表の論理構造化）カテゴリA/Bの実装。"""
import math

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.associators.llm_helper import try_llm_augment
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.shape import BoundingBox
from dxf_extractor.models.table import Table

# 既定の表ヘッダーキーワードは config.keywords.effective_table_headers() が供給する（US1 / FR-101）。


def _bbox_contains_point(bbox: BoundingBox, x: float, y: float) -> bool:
    return bbox.min_x <= x <= bbox.max_x and bbox.min_y <= y <= bbox.max_y


def _bbox_overlap(a: BoundingBox, b: BoundingBox) -> bool:
    return a.min_x <= b.max_x and a.max_x >= b.min_x and a.min_y <= b.max_y and a.max_y >= b.min_y


def _find_containing_block(table: Table, blocks: list[LogicalBlock]) -> LogicalBlock | None:
    for block in blocks:
        if _bbox_contains_point(block.bounding_box, table.position.x, table.position.y):
            return block
    return None


def _is_header_cell(text: str, headers: list[str]) -> bool:
    for kw in headers:
        if kw in text:
            return True
    return False


class Rule3TableStructure(AssociatorBase):
    """Rule3: 表の論理構造化（カテゴリA）。"""

    RULE_ID = "3"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """テーブルの境界識別・ヘッダー特定・列名対応付けを実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []

        for table in drawing.tables:
            # Rule 3-0: テーブル境界識別（テーブルを含むブロックを特定）
            block = _find_containing_block(table, drawing.blocks)
            if block:
                results.append(
                    AssociationResult(
                        rule="3-0",
                        source_id=table.id,
                        target_ids=[block.id],
                        confidence=1.0,
                    )
                )

            if not table.rows:
                continue

            # Rule 3-1: ヘッダー行の特定（キーワードは設定辞書から供給）
            header_row_idx = _identify_header_row(table, config.keywords.effective_table_headers())
            if header_row_idx is not None:
                if llm_config is not None:
                    # カテゴリB: LLMでヘッダー行の精度向上
                    cell_texts = [c.text for row in table.rows for c in row.cells]
                    prompt = f"テーブルのヘッダー行を特定してください。セル: {cell_texts}"
                    result = try_llm_augment(
                        rule_id="3-1",
                        source_id=table.id,
                        prompt=prompt,
                        llm_config=llm_config,
                        fallback_target_ids=[f"row:{header_row_idx}"],
                    )
                    results.append(result)
                else:
                    results.append(
                        AssociationResult(
                            rule="3-1",
                            source_id=table.id,
                            target_ids=[f"row:{header_row_idx}"],
                            confidence=1.0,
                        )
                    )

                # Rule 3-2: 同一行のセル集約（delta_y）
                delta_y = config.tolerances.delta_y_ratio
                results.append(
                    AssociationResult(
                        rule="3-2",
                        source_id=table.id,
                        target_ids=[f"delta_y_ratio:{delta_y}"],
                        confidence=1.0,
                    )
                )

                # Rule 3-3: 列インデックスと列名の対応付け
                header_row = table.rows[header_row_idx]
                col_names = [c.text for c in sorted(header_row.cells, key=lambda c: c.col) if c.text.strip()]
                if col_names:
                    results.append(
                        AssociationResult(
                            rule="3-3",
                            source_id=table.id,
                            target_ids=[f"col:{i}:{name}" for i, name in enumerate(col_names)],
                            confidence=1.0,
                        )
                    )

        return results


def _identify_header_row(table: Table, headers: list[str]) -> int | None:
    """ヘッダー行インデックスを返す。見つからない場合はNone。"""
    for row in table.rows:
        for cell in row.cells:
            if _is_header_cell(cell.text, headers):
                return row.index
    # ヘッダーキーワードが見つからない場合、最初の行をヘッダーとみなす
    if table.rows:
        return table.rows[0].index
    return None
