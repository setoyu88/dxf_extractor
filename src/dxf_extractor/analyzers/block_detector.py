"""DBSCANによる論理ブロック検出（FR-004）。"""
import numpy as np
from sklearn.cluster import DBSCAN

from dxf_extractor.config import ClusteringConfig
from dxf_extractor.models.block import BlockType, LogicalBlock
from dxf_extractor.models.dimension import Dimension
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import BoundingBox, Point2D, Shape


def detect_blocks(
    shapes: list[Shape],
    dimensions: list[Dimension],
    notes: list[Note],
    clustering_config: ClusteringConfig,
    scale_factor: float = 1.0,
) -> list[LogicalBlock]:
    """DBSCAN空間クラスタリングによって論理ブロックを検出する（FR-004）。

    Args:
        shapes: 形状リスト。
        dimensions: 寸法リスト。
        notes: 注記リスト。
        clustering_config: DBSCANパラメータを含む設定。
        scale_factor: 近傍半径 epsilon に乗ずるスケール係数（US3 / FR-301）。既定1.0で現行同一。

    Returns:
        list[LogicalBlock]: 検出した論理ブロックリスト。
    """
    if not shapes:
        return []

    centroids = []
    entity_refs: list[tuple[str, str]] = []

    for s in shapes:
        # 座標情報なし（bounding_box面積ゼロ）の形状は原点付近のクラスターに誤混入するためスキップする
        if s.bounding_box.max_x == s.bounding_box.min_x and s.bounding_box.max_y == s.bounding_box.min_y:
            continue
        cx = (s.bounding_box.min_x + s.bounding_box.max_x) / 2
        cy = (s.bounding_box.min_y + s.bounding_box.max_y) / 2
        centroids.append([cx, cy])
        entity_refs.append(("shape", s.id))

    for d in dimensions:
        centroids.append([d.position.x, d.position.y])
        entity_refs.append(("dimension", d.id))

    for n in notes:
        centroids.append([n.position.x, n.position.y])
        entity_refs.append(("note", n.id))

    X = np.array(centroids)
    db = DBSCAN(
        eps=clustering_config.epsilon * scale_factor,
        min_samples=clustering_config.min_samples,
    ).fit(X)

    labels: np.ndarray = db.labels_

    cluster_map: dict[int, dict[str, list[str]]] = {}
    for idx, label in enumerate(labels):
        if label == -1:
            continue
        entity_type, entity_id = entity_refs[idx]
        if label not in cluster_map:
            cluster_map[label] = {"shape": [], "dimension": [], "note": []}
        cluster_map[label][entity_type].append(entity_id)

    blocks: list[LogicalBlock] = []
    for i, (label, ids) in enumerate(sorted(cluster_map.items())):
        bb = _compute_block_bb(ids["shape"], shapes)
        position = Point2D(x=bb.min_x, y=bb.min_y)
        blocks.append(
            LogicalBlock(
                id=f"block_{i + 1:03d}",
                type=BlockType.part_view,
                position=position,
                bounding_box=bb,
                shape_ids=ids["shape"],
                dimension_ids=ids["dimension"],
                note_ids=ids["note"],
                llm_labeled=False,
            )
        )

    return blocks


def _compute_block_bb(shape_ids: list[str], shapes: list[Shape]) -> BoundingBox:
    """ブロックに含まれる形状のバウンディングボックスを計算する。

    Args:
        shape_ids: ブロックに含まれる形状IDリスト。
        shapes: 全形状リスト。

    Returns:
        BoundingBox: 計算したバウンディングボックス。
    """
    shape_map = {s.id: s for s in shapes}
    xs_min, ys_min, xs_max, ys_max = [], [], [], []
    for sid in shape_ids:
        if sid in shape_map:
            bb = shape_map[sid].bounding_box
            xs_min.append(bb.min_x)
            ys_min.append(bb.min_y)
            xs_max.append(bb.max_x)
            ys_max.append(bb.max_y)

    if not xs_min:
        return BoundingBox(min_x=0, min_y=0, max_x=0, max_y=0)

    return BoundingBox(
        min_x=min(xs_min),
        min_y=min(ys_min),
        max_x=max(xs_max),
        max_y=max(ys_max),
    )
