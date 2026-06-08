"""Rule8（標題欄構造化）カテゴリA/Bの実装。"""
import re

from dxf_extractor.associators.base import AssociatorBase
from dxf_extractor.associators.llm_helper import try_llm_augment
from dxf_extractor.config import LLMConfig, StructurizeConfig
from dxf_extractor.models.association import AssociationResult
from dxf_extractor.models.block import BlockType, LogicalBlock
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.models.note import Note

_LABEL_FIELD_MAP = {
    "作成": "metadata.created_by",
    "設計": "metadata.designed_by",
    "照査": "metadata.checked_by",
    "承認": "metadata.approved_by",
    "材料": "metadata.material",
    "尺度": "metadata.scale",
    "Scale": "metadata.scale",
    "scale": "metadata.scale",
    "Title": "metadata.title",
    "title": "metadata.title",
    "図面番号": "metadata.drawing_number",
    "DRAWING": "metadata.drawing_number",
}

# 水平マッチング: y差の許容値（DXF単位）
_HORIZ_Y_TOL = 3.0
# 垂直マッチング: x差の許容値（DXF単位）
_VERT_X_TOL = 15.0


def _find_title_block(blocks: list[LogicalBlock]) -> list[LogicalBlock]:
    """標題欄ブロックを探す（table型ブロックのうち最も下方のもの）。"""
    table_blocks = [b for b in blocks if b.type == BlockType.table]
    if not table_blocks:
        return []
    min_y = min(b.bounding_box.min_y for b in table_blocks)
    return [b for b in table_blocks if b.bounding_box.min_y == min_y]


def _get_title_block_notes(drawing: DXFDrawing, region: str = "bottom", ratio: float = 0.2) -> list[Note]:
    """最下端tableブロックのbbox内のノートを返す。ブロックがない場合はプロファイルの領域にフォールバック。

    Args:
        drawing: 入力DXF図面。
        region: 標題欄探索領域（bottom/top/top_right/bottom_right/auto）。既定は下部。
        ratio: 探索帯の幅・高さ比（既定0.2＝現行の下端20%）。
    """
    title_blocks = _find_title_block(drawing.blocks)
    if title_blocks:
        bbox = title_blocks[0].bounding_box
        return [
            n for n in drawing.notes
            if bbox.min_x <= n.position.x <= bbox.max_x
            and bbox.min_y <= n.position.y <= bbox.max_y
        ]

    # フォールバック: プロファイルで指定した領域（既定は図面下端20%エリア＝現行挙動）
    return _notes_in_region(drawing.notes, region, ratio)


def _notes_in_region(notes: list[Note], region: str, ratio: float) -> list[Note]:
    """指定領域（標題欄プロファイル）に含まれるノートを返す。"""
    if not notes:
        return []
    xs = [n.position.x for n in notes]
    ys = [n.position.y for n in notes]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    low_y = y_min + (y_max - y_min) * ratio          # 下部帯の上限
    high_y = y_max - (y_max - y_min) * ratio         # 上部帯の下限
    right_x = x_max - (x_max - x_min) * ratio        # 右部帯の左限

    def in_region(n: Note) -> bool:
        if region == "bottom":
            return n.position.y <= low_y
        if region == "top":
            return n.position.y >= high_y
        if region == "top_right":
            return n.position.y >= high_y and n.position.x >= right_x
        if region == "bottom_right":
            return n.position.y <= low_y and n.position.x >= right_x
        # auto: 領域で絞らず全ノートを対象とする
        return True

    return [n for n in notes if in_region(n)]


def _find_value_note(label: Note, candidates: list[Note], label_notes: list[Note]) -> Note | None:
    """ラベルノートに対応する値ノートを水平・垂直の両方向から探す。

    水平探索は同じy行にある次のラベルのx座標を境界とし、ラベルをまたいだ誤取得を防ぐ。
    """
    # 同じy行で右側にある次のラベルのx座標を探索上限とする
    next_label_x = min(
        (n.position.x for n in label_notes
         if n.position.x > label.position.x
         and abs(n.position.y - label.position.y) <= _HORIZ_Y_TOL),
        default=float("inf"),
    )

    # 水平方向: 同じy行で右側かつ次のラベルより手前の最も近いもの
    horiz = [
        n for n in candidates
        if abs(n.position.y - label.position.y) <= _HORIZ_Y_TOL
        and label.position.x < n.position.x < next_label_x
    ]
    if horiz:
        return min(horiz, key=lambda n: n.position.x - label.position.x)

    # 垂直方向: 同じx列で下方（y値が小さい）に最も近いもの
    vert = [
        n for n in candidates
        if abs(n.position.x - label.position.x) <= _VERT_X_TOL
        and n.position.y < label.position.y
    ]
    if vert:
        return min(vert, key=lambda n: label.position.y - n.position.y)

    return None


class Rule8TitleBlock(AssociatorBase):
    """Rule8: 標題欄構造化（カテゴリA）。"""

    RULE_ID = "8"

    def associate(
        self,
        drawing: DXFDrawing,
        config: StructurizeConfig,
        llm_config: LLMConfig | None = None,
    ) -> list[AssociationResult]:
        """標題欄領域特定・ラベル値ペア認識・NTS識別を実行する。

        Args:
            drawing: 入力DXF図面。
            config: 体系化処理設定。
            llm_config: LLM設定（Noneの場合カテゴリAのみ）。

        Returns:
            list[AssociationResult]: 関連付け結果リスト。
        """
        results: list[AssociationResult] = []

        # Rule 8-1: 標題欄領域の特定
        title_blocks = _find_title_block(drawing.blocks)
        for block in title_blocks:
            results.append(
                AssociationResult(
                    rule="8-1",
                    source_id=block.id,
                    target_ids=["metadata.title_block"],
                    confidence=1.0,
                )
            )

        # 標題欄エリアのノートを収集（bboxベース、レイヤー名に依存しない。領域はプロファイル指定）
        title_notes = _get_title_block_notes(
            drawing, config.profile.title_block_region, config.profile.title_block_ratio
        )
        label_notes = [n for n in title_notes if _match_label(n.text)]
        non_label_candidates = [n for n in title_notes if not _match_label(n.text)]

        # Rule 8-2: ラベル-値ペアの認識（カテゴリA/B）
        for note in title_notes:
            field = _match_label(note.text)
            if not field:
                continue

            if llm_config is not None:
                # カテゴリA結果をフォールバック値として事前取得
                value_note = _find_value_note(note, non_label_candidates, label_notes)
                fallback_val = value_note.text if value_note else None
                prompt = f"標題欄のラベル '{note.text}' に対応する値テキストのみを1行で返してください。フィールド: {field}"
                result = try_llm_augment(
                    rule_id="8-2",
                    source_id=note.id,
                    prompt=prompt,
                    llm_config=llm_config,
                    fallback_target_ids=[field],
                    extract_value=lambda content: content.strip() or None,
                    fallback_extracted_value=fallback_val,
                )
                results.append(result)
            else:
                value_note = _find_value_note(note, non_label_candidates, label_notes)
                if value_note:
                    results.append(
                        AssociationResult(
                            rule="8-2",
                            source_id=note.id,
                            target_ids=[field],
                            extracted_value=value_note.text,
                            confidence=1.0,
                        )
                    )

        # Rule 8-3: NTS識別
        for note in drawing.notes:
            if note.text.strip().upper() == "NTS":
                results.append(
                    AssociationResult(
                        rule="8-3",
                        source_id=note.id,
                        target_ids=["metadata.scale"],
                        extracted_value="NTS",
                        confidence=1.0,
                    )
                )

        return results


def _match_label(text: str) -> str | None:
    """ラベルテキストに対応するフィールド名を返す。マッチしない場合はNone。"""
    stripped = text.strip().rstrip("：:").strip()
    for label, field in _LABEL_FIELD_MAP.items():
        if label in stripped:
            return field
    return None
