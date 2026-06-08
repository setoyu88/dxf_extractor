"""レイヤ情報・含有エンティティ種別・エンティティ数の抽出（FR-010）。"""
from collections import defaultdict
from typing import Iterable

from ezdxf.document import Drawing

from dxf_extractor.config import KeywordConfig
from dxf_extractor.models.layer import Layer, LayerPurpose
from dxf_extractor.utils import sanitize_surrogates


def extract_layers(
    doc: Drawing,
    keywords: KeywordConfig | None = None,
    entities: Iterable | None = None,
) -> list[Layer]:
    """DXF文書からレイヤ情報を抽出する（FR-010）。

    Args:
        doc: ezdxf Drawing オブジェクト。
        keywords: レイヤ用途判定に用いるキーワード辞書（US1 / FR-101）。
            None の場合は既定辞書（現行と同一）を用いる。
        entities: レイヤ集計に用いるエンティティ列（US2 / 複数シート対応）。
            None の場合はモデルスペースのみを集計（従来挙動）。

    Returns:
        list[Layer]: 抽出したレイヤ情報リスト。
    """
    if keywords is None:
        keywords = KeywordConfig()
    if entities is None:
        entities = doc.modelspace()

    layer_types: dict[str, set[str]] = defaultdict(set)
    layer_counts: dict[str, int] = defaultdict(int)

    for entity in entities:
        try:
            layer_name = sanitize_surrogates(entity.dxf.get("layer", "0"))
            dxf_type = entity.dxftype()
            layer_types[layer_name].add(dxf_type)
            layer_counts[layer_name] += 1
        except Exception:
            pass

    layers: list[Layer] = []
    for layer_name in set(layer_types) | set(layer_counts):
        purpose = _infer_purpose(layer_name, keywords)
        layers.append(
            Layer(
                name=layer_name,
                entity_types=sorted(layer_types.get(layer_name, set())),
                entity_count=layer_counts.get(layer_name, 0),
                purpose=purpose,
                llm_labeled=False,
            )
        )

    return sorted(layers, key=lambda l: l.name)


def _infer_purpose(layer_name: str, keywords: KeywordConfig) -> LayerPurpose:
    """レイヤ名からキーワード辞書で用途を推定する。

    Args:
        layer_name: レイヤ名。
        keywords: キーワード辞書。

    Returns:
        LayerPurpose: 推定した用途。不明な場合は その他 を返す。
    """
    purpose_name = keywords.resolve_layer_purpose(layer_name)
    if purpose_name is None:
        return LayerPurpose.その他
    return LayerPurpose(purpose_name)
