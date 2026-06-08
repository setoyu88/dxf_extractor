"""矩形ポリライン＋テキスト密度ヒューリスティックによる図枠候補検出（FR-004）。"""
from dxf_extractor.models.block import LogicalBlock
from dxf_extractor.models.layer import Layer, LayerPurpose
from dxf_extractor.models.shape import Shape

_MIN_AREA_RATIO = 0.3
_MIN_NOTE_COUNT = 2


def detect_frames(
    blocks: list[LogicalBlock],
    shapes: list[Shape],
    layers: list[Layer] | None = None,
) -> list[int]:
    """論理ブロックの中から図枠候補のインデックスを返す。

    図枠用レイヤー（purpose=図枠）を含むブロックは面積比条件を緩和して判定する。
    レイヤー情報がない場合は面積比ヒューリスティックにフォールバックする。

    Args:
        blocks: 論理ブロックリスト。
        shapes: 全形状リスト（面積計算のみ使用）。
        layers: レイヤー情報リスト。purposeフィールドから図枠レイヤーを特定する。

    Returns:
        list[int]: 図枠候補のブロックインデックスリスト。
    """
    if not blocks:
        return []

    all_bb = _total_bounding_box(blocks)
    if all_bb is None:
        return []

    total_area = (all_bb[2] - all_bb[0]) * (all_bb[3] - all_bb[1])
    if total_area <= 0:
        return []

    frame_layer_names: set[str] = set()
    if layers:
        frame_layer_names = {l.name for l in layers if l.purpose == LayerPurpose.図枠}

    frame_shape_ids: set[str] = set()
    if frame_layer_names:
        frame_shape_ids = {s.id for s in shapes if s.layer in frame_layer_names}

    frame_indices: list[int] = []
    for i, block in enumerate(blocks):
        bb = block.bounding_box
        block_area = (bb.max_x - bb.min_x) * (bb.max_y - bb.min_y)
        area_ratio = block_area / total_area

        has_frame_shape = bool(frame_shape_ids) and any(
            sid in frame_shape_ids for sid in block.shape_ids
        )
        # 図枠レイヤーの形状を含むブロックは面積比条件を緩和して判定する
        if has_frame_shape and len(block.note_ids) >= _MIN_NOTE_COUNT:
            frame_indices.append(i)
            continue
        # 図枠レイヤーが特定できない場合は面積比ヒューリスティックにフォールバックする
        if area_ratio >= _MIN_AREA_RATIO and len(block.note_ids) >= _MIN_NOTE_COUNT:
            frame_indices.append(i)

    return frame_indices


def _total_bounding_box(blocks: list[LogicalBlock]) -> tuple[float, float, float, float] | None:
    """全ブロックを包含するバウンディングボックスを計算する。

    Args:
        blocks: 論理ブロックリスト。

    Returns:
        tuple[float, float, float, float] | None: (min_x, min_y, max_x, max_y)。
    """
    if not blocks:
        return None
    xs_min = [b.bounding_box.min_x for b in blocks]
    ys_min = [b.bounding_box.min_y for b in blocks]
    xs_max = [b.bounding_box.max_x for b in blocks]
    ys_max = [b.bounding_box.max_y for b in blocks]
    return min(xs_min), min(ys_min), max(xs_max), max(ys_max)
