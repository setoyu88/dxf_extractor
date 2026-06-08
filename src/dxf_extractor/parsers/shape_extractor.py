"""LINE/ARC/CIRCLE/POLYLINE/OtherGeometry形状抽出。"""
from typing import Iterable

from dxf_extractor.parsers.entity_source import sheet_of, source_block_of
from dxf_extractor.utils import sanitize_surrogates
from dxf_extractor.models.shape import (
    ArcGeometry,
    BoundingBox,
    CircleGeometry,
    LineGeometry,
    OtherGeometry,
    Point2D,
    PolylineGeometry,
    Shape,
)

_SUPPORTED_TYPES = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE", "POINT", "LEADER", "HATCH"}


def extract_shapes(entities: Iterable) -> list[Shape]:
    """エンティティ列から全形状エンティティを抽出する。

    Args:
        entities: 反復対象エンティティ列（モデルスペース、または entity_source が供給する
            INSERT展開・複数シート反映済みのリスト）。

    Returns:
        list[Shape]: 抽出した形状リスト。
    """
    shapes: list[Shape] = []
    counter = 1

    for entity in entities:
        dxf_type = entity.dxftype()
        try:
            shape = _extract_entity(entity, dxf_type, counter)
            if shape is not None:
                _tag_sheet_source(shape, entity)
                shapes.append(shape)
                counter += 1
        except Exception:
            # 個別エンティティのエラーはOtherGeometryとして記録
            shape = _to_other(entity, dxf_type, counter)
            _tag_sheet_source(shape, entity)
            shapes.append(shape)
            counter += 1

    return shapes


def _tag_sheet_source(shape: Shape, entity: object) -> None:
    """形状に帰属シート・由来ブロック（INSERT展開時）を付与する（US2 / FR-204/205）。"""
    shape.sheet = sheet_of(entity)
    if isinstance(shape.geometry, OtherGeometry):
        shape.geometry.source_block = source_block_of(entity)


def _extract_entity(entity: object, dxf_type: str, counter: int) -> Shape | None:
    """エンティティ種別に応じてShapeを生成する。

    Args:
        entity: ezdxf エンティティ。
        dxf_type: エンティティ種別文字列。
        counter: ID採番用カウンター。

    Returns:
        Shape | None: 生成したShapeオブジェクト。テキスト等の非形状エンティティはNone。
    """
    layer = sanitize_surrogates(entity.dxf.get("layer", "0"))  # type: ignore[attr-defined]
    shape_id = f"shape_{counter:03d}"

    if dxf_type == "LINE":
        start = entity.dxf.start  # type: ignore[attr-defined]
        end = entity.dxf.end  # type: ignore[attr-defined]
        geom = LineGeometry(
            start=Point2D(x=float(start.x), y=float(start.y)),
            end=Point2D(x=float(end.x), y=float(end.y)),
        )
        bb = _bb_from_points([start, end])
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type == "CIRCLE":
        center = entity.dxf.center  # type: ignore[attr-defined]
        r = float(entity.dxf.radius)  # type: ignore[attr-defined]
        geom = CircleGeometry(center=Point2D(x=float(center.x), y=float(center.y)), radius=r)
        bb = BoundingBox(
            min_x=center.x - r,
            min_y=center.y - r,
            max_x=center.x + r,
            max_y=center.y + r,
        )
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type == "ARC":
        center = entity.dxf.center  # type: ignore[attr-defined]
        r = float(entity.dxf.radius)  # type: ignore[attr-defined]
        geom = ArcGeometry(
            center=Point2D(x=float(center.x), y=float(center.y)),
            radius=r,
            start_angle=float(entity.dxf.start_angle),  # type: ignore[attr-defined]
            end_angle=float(entity.dxf.end_angle),  # type: ignore[attr-defined]
        )
        bb = BoundingBox(
            min_x=center.x - r,
            min_y=center.y - r,
            max_x=center.x + r,
            max_y=center.y + r,
        )
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type in ("LWPOLYLINE", "POLYLINE"):
        vertices = _get_polyline_vertices(entity, dxf_type)
        is_closed = bool(getattr(entity, "is_closed", False))
        geom = PolylineGeometry(vertices=vertices, is_closed=is_closed)
        if vertices:
            xs = [v.x for v in vertices]
            ys = [v.y for v in vertices]
            bb = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
        else:
            bb = BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0)
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type == "LEADER":
        vertices = [Point2D(x=float(v.x), y=float(v.y)) for v in entity.vertices]  # type: ignore[attr-defined]
        if vertices:
            xs = [v.x for v in vertices]
            ys = [v.y for v in vertices]
            bb = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
        else:
            bb = BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0)
        geom = PolylineGeometry(vertices=vertices, is_closed=False)
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type == "HATCH":
        xs, ys = [], []
        for path in entity.paths:  # type: ignore[attr-defined]
            for pt in getattr(path, "control_points", []):
                xs.append(float(pt.x))
                ys.append(float(pt.y))
            for edge in getattr(path, "edges", []):
                for attr in ("start", "end", "center"):
                    pt = getattr(edge, attr, None)
                    if pt is not None:
                        xs.append(float(pt.x))
                        ys.append(float(pt.y))
        if xs and ys:
            bb = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
        else:
            bb = BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0)
        geom = OtherGeometry(entity_type="HATCH", raw_attributes={})
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type == "SPLINE":
        try:
            pts = list(entity.control_points)  # type: ignore[attr-defined]
            vertices = [Point2D(x=float(p[0]), y=float(p[1])) for p in pts]
        except Exception:
            vertices = []
        if vertices:
            xs = [v.x for v in vertices]
            ys = [v.y for v in vertices]
            bb = BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
        else:
            bb = BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0)
        geom = PolylineGeometry(vertices=vertices, is_closed=False)
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    if dxf_type == "ELLIPSE":
        try:
            center = entity.dxf.center  # type: ignore[attr-defined]
            major_axis = entity.dxf.major_axis  # type: ignore[attr-defined]
            ratio = float(entity.dxf.ratio)  # type: ignore[attr-defined]
            vx = float(major_axis.x)
            vy = float(major_axis.y)
            # 回転楕円のバウンディングボックス半径を正確に計算する
            x_half = (vx**2 + (ratio * vy) ** 2) ** 0.5
            y_half = (vy**2 + (ratio * vx) ** 2) ** 0.5
            raw = {
                "center": f"{float(center.x):.4f},{float(center.y):.4f}",
                "major_axis": f"{vx:.4f},{vy:.4f}",
                "ratio": str(ratio),
            }
            bb = BoundingBox(
                min_x=float(center.x) - x_half,
                min_y=float(center.y) - y_half,
                max_x=float(center.x) + x_half,
                max_y=float(center.y) + y_half,
            )
        except Exception:
            raw = {}
            bb = BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0)
        geom = OtherGeometry(entity_type="ELLIPSE", raw_attributes=raw)
        return Shape(id=shape_id, layer=layer, bounding_box=bb, geometry=geom)

    # テキスト系・寸法系エンティティは形状として扱わない
    if dxf_type in ("TEXT", "MTEXT", "DIMENSION", "INSERT"):
        return None

    # サポート対象外エンティティはOtherGeometryとして記録
    return _to_other(entity, dxf_type, counter)


def _get_polyline_vertices(entity: object, dxf_type: str) -> list[Point2D]:
    """ポリラインの頂点リストを取得する。

    Args:
        entity: ezdxf ポリラインエンティティ。
        dxf_type: "LWPOLYLINE" or "POLYLINE"。

    Returns:
        list[Point2D]: 頂点リスト。
    """
    vertices: list[Point2D] = []
    if dxf_type == "LWPOLYLINE":
        for point in entity.get_points():  # type: ignore[attr-defined]
            vertices.append(Point2D(x=float(point[0]), y=float(point[1])))
    else:
        for v in entity.vertices:  # type: ignore[attr-defined]
            loc = v.dxf.location
            vertices.append(Point2D(x=float(loc.x), y=float(loc.y)))
    return vertices


def _to_other(entity: object, dxf_type: str, counter: int) -> Shape:
    """エンティティをOtherGeometryのShapeに変換する。

    Args:
        entity: ezdxf エンティティ。
        dxf_type: エンティティ種別文字列。
        counter: ID採番用カウンター。

    Returns:
        Shape: OtherGeometryを持つShape。
    """
    layer = sanitize_surrogates(entity.dxf.get("layer", "0"))  # type: ignore[attr-defined]
    raw: dict[str, str] = {}
    try:
        for key in entity.dxf.attribs:  # type: ignore[attr-defined]
            try:
                raw[key] = sanitize_surrogates(str(entity.dxf.get(key)))
            except Exception:
                pass
    except Exception:
        pass
    geom = OtherGeometry(entity_type=dxf_type, raw_attributes=raw)
    return Shape(
        id=f"shape_{counter:03d}",
        layer=layer,
        bounding_box=BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0),
        geometry=geom,
    )


def _bb_from_points(points: list) -> BoundingBox:
    """点リストからバウンディングボックスを計算する。

    Args:
        points: ezdxf Vectorオブジェクトのリスト。

    Returns:
        BoundingBox: 計算したバウンディングボックス。
    """
    xs = [float(p.x) for p in points]
    ys = [float(p.y) for p in points]
    return BoundingBox(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
