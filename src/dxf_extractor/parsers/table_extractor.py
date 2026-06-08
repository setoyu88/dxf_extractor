"""矩形ポリライン格子からの表検出・セル抽出（FR-008）。"""
from typing import Iterable

from dxf_extractor.parsers.entity_source import sheet_of
from dxf_extractor.models.shape import BoundingBox, Point2D
from dxf_extractor.models.table import Table, TableCell, TableRow

_MIN_CELLS = 2
_TOLERANCE = 1.0
_MIN_GRID_INTERSECTIONS = 4
_CELL_Y_TOLERANCE = 2.0


def extract_tables(entities: Iterable) -> list[Table]:
    """エンティティ列から表候補を検出してセル構造を抽出する（FR-008）。

    LWPOLYLINEの閉じた矩形とLINEエンティティの格子構造を両方検出する。

    Args:
        entities: 反復対象エンティティ列（entity_source 供給または モデルスペース）。

    Returns:
        list[Table]: 抽出した表リスト。
    """
    # 複数回走査するためリスト化する（ジェネレータ・モデルスペースの双方に対応）。
    entities = list(entities)
    tables: list[Table] = []
    counter = 1

    rects = _find_closed_rectangles(entities) + _find_table_grid_bb(entities)

    for rect in rects:
        inner_texts = _texts_inside(entities, rect)
        if len(inner_texts) < _MIN_CELLS:
            continue

        rows = _assign_cells(inner_texts)
        if not rows:
            continue

        position = Point2D(x=rect.min_x, y=rect.max_y)
        tables.append(
            Table(
                id=f"table_{counter:03d}",
                rows=rows,
                position=position,
                bounding_box=rect,
                layer="0",
                sheet=_rect_sheet(entities, rect),
            )
        )
        counter += 1

    return tables


def _rect_sheet(entities: Iterable, rect: BoundingBox) -> str | None:
    """矩形内に位置するエンティティの帰属シートを返す（US2 / FR-204）。

    複数シート処理が無効な場合は注釈が無く None を返す（従来挙動）。
    """
    for entity in entities:
        sheet = sheet_of(entity)
        if sheet is None:
            continue
        try:
            insert = entity.dxf.get("insert", None) or entity.dxf.get("start", None)  # type: ignore[attr-defined]
            if insert is not None and rect.min_x <= float(insert.x) <= rect.max_x and rect.min_y <= float(insert.y) <= rect.max_y:
                return sheet
        except Exception:
            continue
    return None


def _find_closed_rectangles(entities: Iterable) -> list[BoundingBox]:
    """エンティティ列から閉じた矩形ポリラインを検出する。

    Args:
        entities: 反復対象エンティティ列。

    Returns:
        list[BoundingBox]: 検出した矩形領域リスト。
    """
    rects: list[BoundingBox] = []
    for entity in entities:
        if entity.dxftype() != "LWPOLYLINE":
            continue
        try:
            if not entity.is_closed:  # type: ignore[attr-defined]
                continue
            points = list(entity.get_points())  # type: ignore[attr-defined]
            if len(points) < 4:
                continue
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            bb = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
            if (bb.max_x - bb.min_x) > _TOLERANCE and (bb.max_y - bb.min_y) > _TOLERANCE:
                rects.append(bb)
        except Exception:
            pass
    return rects


def _find_table_grid_bb(entities: Iterable) -> list[BoundingBox]:
    """LINE群の格子構造からテーブル領域のbounding_boxを検出する。

    水平線と垂直線が _MIN_GRID_INTERSECTIONS 以上交差する領域をテーブルとみなす。

    Args:
        entities: 反復対象エンティティ列。

    Returns:
        list[BoundingBox]: 検出したテーブル領域リスト。
    """
    h_lines: list[tuple[float, float, float]] = []
    v_lines: list[tuple[float, float, float]] = []
    for entity in entities:
        if entity.dxftype() != "LINE":
            continue
        try:
            s, e = entity.dxf.start, entity.dxf.end  # type: ignore[attr-defined]
            if abs(s.y - e.y) < 0.5:
                h_lines.append((min(s.x, e.x), max(s.x, e.x), s.y))
            elif abs(s.x - e.x) < 0.5:
                v_lines.append((s.x, min(s.y, e.y), max(s.y, e.y)))
        except Exception:
            pass

    if not h_lines or not v_lines:
        return []

    intersections = sum(
        1
        for hx0, hx1, hy in h_lines
        for vx, vy0, vy1 in v_lines
        if hx0 <= vx <= hx1 and vy0 <= hy <= vy1
    )
    if intersections < _MIN_GRID_INTERSECTIONS:
        return []

    xs = [x for x, _, _ in v_lines]
    ys = [y for _, _, y in h_lines]
    return [BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))]


def _texts_inside(entities: Iterable, rect: BoundingBox) -> list[tuple[str, float, float]]:
    """指定した矩形内に含まれるテキストエンティティを取得する。

    Args:
        entities: 反復対象エンティティ列。
        rect: 対象の矩形領域。

    Returns:
        list[tuple[str, float, float]]: (テキスト, x座標, y座標) のリスト。
    """
    texts: list[tuple[str, float, float]] = []
    for entity in entities:
        dxf_type = entity.dxftype()
        if dxf_type not in ("TEXT", "MTEXT"):
            continue
        try:
            if dxf_type == "TEXT":
                text = entity.dxf.get("text", "") or ""  # type: ignore[attr-defined]
                insert = entity.dxf.insert  # type: ignore[attr-defined]
            else:
                text = entity.text or ""  # type: ignore[attr-defined]
                insert = entity.dxf.insert  # type: ignore[attr-defined]
            if not text:
                continue
            x, y = float(insert.x), float(insert.y)
            if rect.min_x <= x <= rect.max_x and rect.min_y <= y <= rect.max_y:
                texts.append((text, x, y))
        except Exception:
            pass
    return texts


def _assign_cells(texts: list[tuple[str, float, float]]) -> list[TableRow]:
    """テキスト位置から行列を推定してTableRowリストを生成する。

    y座標は許容誤差内でクラスタリングして同一行に割り当てる。

    Args:
        texts: (テキスト, x, y) のリスト。

    Returns:
        list[TableRow]: 行・列インデックスが付いたTableRowリスト。
    """
    if not texts:
        return []

    raw_ys = [y for _, _, y in texts]
    y_cluster = _cluster_ys(raw_ys, _CELL_Y_TOLERANCE)
    xs = sorted({round(x, 0) for _, x, _ in texts})
    x_to_col = {x: i for i, x in enumerate(xs)}

    row_map: dict[float, list[TableCell]] = {}
    for text, x, y in texts:
        repr_y = y_cluster[y]
        col_idx = x_to_col.get(round(x, 0), 0)
        cell = TableCell(row=0, col=col_idx, text=text, position=Point2D(x=x, y=y))
        row_map.setdefault(repr_y, []).append(cell)

    sorted_ys = sorted(row_map.keys(), reverse=True)
    y_to_row_idx = {y: i for i, y in enumerate(sorted_ys)}

    result: list[TableRow] = []
    for repr_y in sorted_ys:
        row_idx = y_to_row_idx[repr_y]
        cells = [
            TableCell(row=row_idx, col=c.col, text=c.text, position=c.position)
            for c in row_map[repr_y]
        ]
        result.append(TableRow(index=row_idx, cells=sorted(cells, key=lambda c: c.col)))
    return result


def _cluster_ys(ys_raw: list[float], tolerance: float) -> dict[float, float]:
    """生のy座標を許容誤差内でクラスタリングし、代表y座標にマッピングする。

    Args:
        ys_raw: 元のy座標リスト。
        tolerance: 同一行とみなす最大距離。

    Returns:
        dict[float, float]: 元のy座標 → 代表y座標のマッピング。
    """
    sorted_ys = sorted(set(ys_raw), reverse=True)
    clusters: list[float] = []
    for y in sorted_ys:
        if not clusters or abs(y - clusters[-1]) > tolerance:
            clusters.append(y)
    return {y: min(clusters, key=lambda c: abs(c - y)) for y in ys_raw}
