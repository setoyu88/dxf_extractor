"""Rule4（断面表示関連付け）カテゴリAの実装。"""
import math
import re

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.note import Note

# 断面識別子パターン: "A-A", "B-B" または単一文字 "A", "B"
_SECTION_ID_PATTERN = re.compile(r"^([A-Z])-\1$|^[A-Z]$")
# 断面レイヤキーワードは config.keywords.effective_section() が供給する（US1 / FR-101）。


def _is_section_layer(layer: str, sections: list[str]) -> bool:
    return any(kw.lower() in layer.lower() for kw in sections)


def _extract_section_letter(text: str, section_pattern: "re.Pattern | None" = None) -> str | None:
    """テキストから断面記号を抽出する。

    既定の英字パターン（A-A／単一英字／断面A-A）で抽出を試み、見つからない場合は
    プロファイルの断面記号パターン（US4 / FR-401。数字断面等）でも抽出を試みる。
    """
    text = text.strip()
    m = re.match(r"^([A-Z])-[A-Z]$", text)
    if m:
        return m.group(1)
    if re.match(r"^[A-Z]$", text):
        return text
    # "断面A-A" パターン
    m2 = re.search(r"([A-Z])-\1", text)
    if m2:
        return m2.group(1)
    # プロファイル指定パターン（既定と異なる流儀＝数字断面・DETAIL等）
    if section_pattern is not None:
        pm = section_pattern.match(text)
        if pm:
            return pm.group(pm.lastindex) if pm.lastindex else pm.group(0)
    return None


def _find_section_block(letter: str, blocks: list[LogicalBlock]) -> LogicalBlock | None:
    """断面図ブロックを名前で探す。"""
    for block in blocks:
        if block.name and letter.upper() in block.name.upper():
            return block
    return None


def _distance(n1: Note, b: LogicalBlock) -> float:
    cx = (b.bounding_box.min_x + b.bounding_box.max_x) / 2
    cy = (b.bounding_box.min_y + b.bounding_box.max_y) / 2
    return math.sqrt((n1.position.x - cx) ** 2 + (n1.position.y - cy) ** 2)


class Rule4CrossSection(AssociatorBase):
    """Rule4: 断面表示関連付け（カテゴリA）。"""

    RULE_ID = "4"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """断面識別子抽出・断面図ラベル特定・切断線方向関係を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []
        sections = config.keywords.effective_section()
        section_pat = config.profile.compiled_section_pattern()

        for note in drawing.notes:
            letter = _extract_section_letter(note.text.strip(), section_pat)
            if letter is None:
                continue

            # Rule 4-1: 断面識別子の抽出（断面レイヤーまたはテキストパターン一致）
            if _is_section_layer(note.layer, sections) or section_pat.match(note.text.strip()):
                results.append(
                    AssociationResult(
                        rule="4-1",
                        source_id=note.id,
                        target_ids=[f"section:{letter}"],
                        confidence=1.0,
                    )
                )

                # Rule 4-2: 断面図ラベルと断面図ブロックの紐づけ
                section_block = _find_section_block(letter, drawing.blocks)
                if section_block:
                    results.append(
                        AssociationResult(
                            rule="4-2",
                            source_id=note.id,
                            target_ids=[section_block.id],
                            confidence=1.0,
                        )
                    )
                else:
                    # ラベルのテキストを対象にブロックを探す（近傍ブロック）
                    candidates = drawing.blocks
                    if candidates:
                        nearest = min(candidates, key=lambda b: _distance(note, b))
                        results.append(
                            AssociationResult(
                                rule="4-2",
                                source_id=note.id,
                                target_ids=[nearest.id],
                                confidence=0.7,
                            )
                        )

                # Rule 4-3: 切断線と断面図の方向関係
                results.append(
                    AssociationResult(
                        rule="4-3",
                        source_id=note.id,
                        target_ids=[f"direction:unknown"],
                        confidence=0.8,
                    )
                )

        return results
