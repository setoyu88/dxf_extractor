"""DXFDrawing ↔ JSON シリアライザ。

抽出フェーズ(a)の出力（抽出JSON）と体系化フェーズ(b)の入力を相互変換する。
スキーマは現行の中間抽出JSON（``DXFDrawing`` の ``model_dump_json``）と同一で、
``serialize`` ↔ ``deserialize`` はロスレスに往復する（FR-003 / 契約 extraction_json.md）。
"""
import json
from pathlib import Path

from dxf_extractor.models.drawing import DXFDrawing


def serialize_to_json(drawing: DXFDrawing) -> str:
    """DXFDrawingをJSON文字列に変換する（SC-005準拠）。

    Args:
        drawing: シリアライズするDXFDrawingオブジェクト。

    Returns:
        str: JSON文字列（インデント付き）。
    """
    return drawing.model_dump_json(indent=2)


def write_json(drawing: DXFDrawing, output_path: Path) -> None:
    """DXFDrawingをJSONファイルに書き出す。

    Args:
        drawing: シリアライズするDXFDrawingオブジェクト。
        output_path: 出力先JSONファイルパス。

    Raises:
        OSError: ファイルの書き込みに失敗した場合。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = serialize_to_json(drawing)
    output_path.write_text(json_str, encoding="utf-8")


def deserialize_from_json(text: str) -> DXFDrawing:
    """抽出JSON文字列を ``DXFDrawing`` に復元する（フェーズ(b)入力）。

    Args:
        text: 抽出JSON文字列。

    Returns:
        DXFDrawing: 復元した抽出データ。

    Raises:
        pydantic.ValidationError: スキーマ不一致・必須欠落の場合。
        ValueError: JSONとして不正な場合（json.JSONDecodeError を含む）。
    """
    return DXFDrawing.model_validate_json(text)


def load_drawing(input_path: Path) -> DXFDrawing:
    """抽出JSONファイルを読み込んで ``DXFDrawing`` に復元する（フェーズ(b)入力）。

    Args:
        input_path: 抽出JSONファイルパス。

    Returns:
        DXFDrawing: 復元した抽出データ。

    Raises:
        OSError: ファイルの読み込みに失敗した場合。
        pydantic.ValidationError: スキーマ不一致・必須欠落の場合。
        ValueError: JSONとして不正な場合。
    """
    text = input_path.read_text(encoding="utf-8")
    return deserialize_from_json(text)
