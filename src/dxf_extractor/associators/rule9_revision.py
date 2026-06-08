"""Rule9（改定情報抽出）カテゴリA/Bの実装。"""
import re

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.associators.llm_helper import try_llm_augment
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import BlockType
from dxf_extractor.models.drawing import DXFDrawing

_REVISION_PATTERN = re.compile(
    r"(?:改定|Rev(?:ision)?)\s*([A-Z])\s*[：:]\s*(.+?)(?=(?:改定|Rev(?:ision)?)\s*[A-Z]\s*[：:]|\\P|$)",
    re.IGNORECASE,
)
_NOTE_HEADER_PATTERN = re.compile(r"^Note[s]?$", re.IGNORECASE)
# 改定キーワードは config.keywords.effective_revision() が供給する（US1 / FR-101）。


def _build_rev_pattern(keywords: list[str]) -> re.Pattern:
    """改定キーワード群から簡易検出用の正規表現を構築する。"""
    alternation = "|".join(re.escape(k) for k in keywords if k)
    return re.compile(alternation, re.IGNORECASE) if alternation else re.compile(r"(?!x)x")


def _extract_revision_text(raw_text: str) -> str:
    """MTEXTの\\Pを改行に展開し、全非空行を返す。"""
    lines = raw_text.replace("\\P", "\n").split("\n")
    results = []
    for line in lines:
        line = line.strip()
        if line:
            results.append(line)
    return "\n".join(results)


class Rule9Revision(AssociatorBase):
    """Rule9: 改定情報抽出（カテゴリA）。"""

    RULE_ID = "9"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """Noteエリア識別と改定情報抽出を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（未使用）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []

        # Rule 9-1: Noteエリアの識別（BlockType.notes のブロック）
        for block in drawing.blocks:
            if block.type == BlockType.notes:
                results.append(
                    AssociationResult(
                        rule="9-1",
                        source_id=block.id,
                        target_ids=["metadata.notes_area"],
                        confidence=1.0,
                    )
                )

        # Noteヘッダーテキストを探してNoteエリアを特定
        note_area_notes = set()
        for note in drawing.notes:
            if _NOTE_HEADER_PATTERN.match(note.text.strip()):
                # このノート周辺のエリアをNoteエリアとみなす
                note_area_notes.add(note.id)
                results.append(
                    AssociationResult(
                        rule="9-1",
                        source_id=note.id,
                        target_ids=["metadata.notes_area"],
                        confidence=1.0,
                    )
                )

        # Rule 9-2: 改定情報の抽出（カテゴリA/B）。キーワードは設定辞書から供給。
        rev_pattern = _build_rev_pattern(config.keywords.effective_revision())
        for note in drawing.notes:
            text = note.text.replace("\\P", "\n")
            if rev_pattern.search(text):
                if llm_config is not None:
                    fallback_val = _extract_revision_text(note.text) or None
                    prompt = f"以下のDXF改定情報テキストから改定内容を抽出し、改行区切りで返してください:\n{text}"
                    result = try_llm_augment(
                        rule_id="9-2",
                        source_id=note.id,
                        prompt=prompt,
                        llm_config=llm_config,
                        fallback_target_ids=["metadata.revision"],
                        extract_value=lambda content: content.strip() or None,
                        fallback_extracted_value=fallback_val,
                    )
                    results.append(result)
                else:
                    extracted = _extract_revision_text(note.text)
                    results.append(
                        AssociationResult(
                            rule="9-2",
                            source_id=note.id,
                            target_ids=["metadata.revision"],
                            extracted_value=extracted if extracted else None,
                            confidence=1.0,
                        )
                    )

        return results
