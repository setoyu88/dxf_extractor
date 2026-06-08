"""図枠テキストからのメタ情報抽出（FR-003）。"""
import re

from dxf_extractor.config import KeywordConfig
from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import Shape

_TITLE_PATTERNS = [
    re.compile(r"図面名[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"名称[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"品名[:：]\s*(.+)", re.IGNORECASE),
]
_DRAWING_NUMBER_PATTERNS = [
    re.compile(r"図番[:：]\s*([A-Za-z0-9\-]+)", re.IGNORECASE),
    re.compile(r"図面番号[:：]\s*([A-Za-z0-9\-]+)", re.IGNORECASE),
    re.compile(r"DWG\s*NO\.?\s*[:：]?\s*([A-Za-z0-9\-]+)", re.IGNORECASE),
]
_REVISION_PATTERNS = [
    re.compile(r"REV\.?\s*[:：]?\s*([A-Za-z0-9]+)", re.IGNORECASE),
    re.compile(r"改訂[:：]\s*([A-Za-z0-9]+)", re.IGNORECASE),
]
_SCALE_PATTERNS = [
    re.compile(r"尺度[:：]\s*([\d:\/]+)", re.IGNORECASE),
    re.compile(r"SCALE\s*[:：]\s*([\d:\/]+)", re.IGNORECASE),
]
_CREATED_BY_PATTERNS = [
    re.compile(r"作成[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"作図[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"DRAWN\s*BY\s*[:：]?\s*(.+)", re.IGNORECASE),
]
_CHECKED_BY_PATTERNS = [
    re.compile(r"確認[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"照査[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"CHECK\s*BY\s*[:：]?\s*(.+)", re.IGNORECASE),
]
_APPROVED_BY_PATTERNS = [
    re.compile(r"承認[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"APPR\.\s*BY\s*[:：]?\s*(.+)", re.IGNORECASE),
]

# ラベルのみのテキスト（値が隣のNoteに存在する形式）に対応するパターン
_LABEL_ONLY_PATTERNS: dict[str, list[re.Pattern]] = {
    "title": [re.compile(r"^(図面名|名称|品名|Title)$", re.IGNORECASE)],
    "drawing_number": [re.compile(r"^(図番|図面番号|DWG\s*NO\.?)$", re.IGNORECASE)],
    "revision": [re.compile(r"^(REV\.?|改訂)$", re.IGNORECASE)],
    "scale": [re.compile(r"^(尺度|SCALE)$", re.IGNORECASE)],
    "created_by": [re.compile(r"^(作成|作図|DRAWN\s*BY)$", re.IGNORECASE)],
    "checked_by": [re.compile(r"^(確認|照査|CHECK\s*BY)$", re.IGNORECASE)],
    "approved_by": [re.compile(r"^(承認|APPR\.)$", re.IGNORECASE)],
}

_PROXIMITY_MAX_DIST = 30.0
_PROXIMITY_MAX_DY = 10.0


def _build_label_only_patterns(keywords: KeywordConfig) -> dict[str, list[re.Pattern]]:
    """既定のラベルのみパターンに、設定の多言語ラベルを追加して返す（US1 / FR-101）。

    既定パターンは常に含むため、設定を与えなければ現行と同一挙動（後方互換）。

    Args:
        keywords: キーワード辞書。`title_block_labels` の各値（ラベル文字列群）を
            完全一致のラベルのみパターンとして追加する。

    Returns:
        dict[str, list[re.Pattern]]: フィールド名→ラベルのみ正規表現のリスト。
    """
    patterns: dict[str, list[re.Pattern]] = {k: list(v) for k, v in _LABEL_ONLY_PATTERNS.items()}
    for field, labels in keywords.effective_title_block_labels().items():
        compiled = patterns.setdefault(field, [])
        for label in labels:
            compiled.append(re.compile(rf"^{re.escape(label)}$", re.IGNORECASE))
    return patterns


def extract_metadata(
    blocks: list[LogicalBlock],
    shapes: list[Shape],
    notes: list[Note],
    frame_indices: list[int],
    keywords: KeywordConfig | None = None,
) -> dict:
    """図枠テキストからメタ情報を抽出する（FR-003）。

    1パス目：ラベルと値が同一テキスト内にある形式をパターンマッチングで抽出する。
    2パス目：ラベルのみのテキストに対し、右隣の近接テキストを値として採用する。

    Args:
        blocks: 論理ブロックリスト。
        shapes: 全形状リスト（未使用、将来の拡張用）。
        notes: 注記テキストリスト。
        frame_indices: 図枠候補ブロックのインデックスリスト。
        keywords: 標題欄ラベルの多言語辞書（US1 / FR-101）。None は既定（現行と同一）。

    Returns:
        dict: メタ情報フィールドの辞書（Metadata コンストラクタに渡す形式）。
    """
    if keywords is None:
        keywords = KeywordConfig()
    label_only_patterns = _build_label_only_patterns(keywords)

    result: dict = {
        "title": None,
        "drawing_number": None,
        "revision": None,
        "scale": None,
        "created_by": None,
        "checked_by": None,
        "approved_by": None,
    }

    note_map = {n.id: n for n in notes}
    candidate_notes: list[Note] = []

    for i in frame_indices:
        if i < len(blocks):
            block = blocks[i]
            for note_id in block.note_ids:
                if note_id in note_map:
                    candidate_notes.append(note_map[note_id])

    if not candidate_notes:
        candidate_notes = list(notes)

    # パス1: ラベルと値が同一テキスト内にある形式
    for note in candidate_notes:
        _try_extract(note.text, _TITLE_PATTERNS, result, "title")
        _try_extract(note.text, _DRAWING_NUMBER_PATTERNS, result, "drawing_number")
        _try_extract(note.text, _REVISION_PATTERNS, result, "revision")
        _try_extract(note.text, _SCALE_PATTERNS, result, "scale")
        _try_extract(note.text, _CREATED_BY_PATTERNS, result, "created_by")
        _try_extract(note.text, _CHECKED_BY_PATTERNS, result, "checked_by")
        _try_extract(note.text, _APPROVED_BY_PATTERNS, result, "approved_by")

    # パス2: ラベルのみのテキストに対し右隣の近接テキストを値として採用する
    for note in candidate_notes:
        for field, label_patterns in label_only_patterns.items():
            if field not in result or result[field] is not None:
                continue
            for pattern in label_patterns:
                if pattern.match(note.text.strip()):
                    value = _find_value_by_proximity(note, candidate_notes)
                    if value:
                        result[field] = value
                    break

    return result


def _try_extract(text: str, patterns: list, result: dict, key: str) -> None:
    """テキストからパターンでメタ情報を抽出し、result辞書に格納する。

    Args:
        text: 検索対象テキスト。
        patterns: 正規表現パターンリスト。
        result: 結果格納辞書。
        key: 格納キー名。
    """
    if result[key] is not None:
        return
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            result[key] = m.group(1).strip()
            return


def _find_value_by_proximity(label_note: Note, candidates: list[Note]) -> str | None:
    """ラベルNoteの右隣に最も近い候補Noteのテキストを値として返す。

    同一行（y座標の差が _PROXIMITY_MAX_DY 未満）かつラベルの右側（dx > 0）にある
    最近傍のNoteを値として採用する。

    Args:
        label_note: ラベルテキストを持つNote。
        candidates: 検索対象のNoteリスト。

    Returns:
        str | None: 値テキスト。見つからない場合はNone。
    """
    best: str | None = None
    best_dist = _PROXIMITY_MAX_DIST
    for note in candidates:
        if note.id == label_note.id:
            continue
        dx = note.position.x - label_note.position.x
        dy = abs(note.position.y - label_note.position.y)
        if dy >= _PROXIMITY_MAX_DY or dx <= 0:
            continue
        dist = (dx**2 + dy**2) ** 0.5
        if dist < best_dist:
            best, best_dist = note.text, dist
    return best
