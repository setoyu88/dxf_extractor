"""TEXT/MTEXT抽出・テキスト寸法検出（注記と寸法を分離）。"""
import re
import unicodedata
from typing import Iterable

from dxf_extractor.parsers.entity_source import sheet_of
from dxf_extractor.utils import sanitize_surrogates

from dxf_extractor.models.dimension import TextDimension
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import BoundingBox, Point2D

_DIMENSION_PATTERN = re.compile(r"^\s*[\+\-]?\d+(\.\d+)?\s*$")
_CHAR_WIDTH_FACTOR = 0.6
_DEFAULT_CHAR_HEIGHT = 2.5


def extract_texts(entities: Iterable) -> tuple[list[Note], list[TextDimension]]:
    """エンティティ列からTEXT/MTEXTを抽出し、注記とテキスト寸法に分類する（FR-006・FR-009・FR-021）。

    Args:
        entities: 反復対象エンティティ列（entity_source 供給または モデルスペース）。

    Returns:
        tuple[list[Note], list[TextDimension]]: (注記リスト, テキスト寸法リスト)。
    """
    notes: list[Note] = []
    text_dims: list[TextDimension] = []
    note_counter = 1
    tdim_counter = 1

    for entity in entities:
        dxf_type = entity.dxftype()
        if dxf_type not in ("TEXT", "MTEXT"):
            continue
        try:
            text_content, insert, height = _get_text_info(entity, dxf_type)
            text_content = sanitize_surrogates(text_content)
            if not text_content:
                continue
            layer = sanitize_surrogates(entity.dxf.get("layer", "0"))  # type: ignore[attr-defined]
            position = Point2D(x=float(insert.x), y=float(insert.y))
            bb = _estimate_bounding_box(text_content, insert, height)

            clean_text = _strip_mtext_codes(text_content) if dxf_type == "MTEXT" else text_content
            if _is_dimension_text(clean_text):
                try:
                    value = float(clean_text.strip())
                    text_dims.append(
                        TextDimension(
                            id=f"tdim_{tdim_counter:03d}",
                            value=value,
                            text=text_content,
                            position=position,
                            bounding_box=bb,
                            layer=layer,
                        )
                    )
                    tdim_counter += 1
                    continue
                except ValueError:
                    pass

            # MTEXTは書式コード除去済みのclean_textをnote.textとして保存する（\P改行含む）
            notes.append(
                Note(
                    id=f"note_{note_counter:03d}",
                    text=clean_text,
                    position=position,
                    bounding_box=bb,
                    layer=layer,
                    entity_type=dxf_type,
                    sheet=sheet_of(entity),
                )
            )
            note_counter += 1
        except Exception:
            note_counter += 1

    return notes, text_dims


def _get_text_info(entity: object, dxf_type: str) -> tuple[str, object, float]:
    """テキストエンティティからテキスト内容・挿入点・文字高さを取得する。

    Args:
        entity: ezdxf テキストエンティティ。
        dxf_type: "TEXT" or "MTEXT"。

    Returns:
        tuple[str, Vector, float]: (テキスト内容, 挿入点, 文字高さ)。
    """
    if dxf_type == "TEXT":
        text = entity.dxf.get("text", "") or ""  # type: ignore[attr-defined]
        insert = entity.dxf.insert  # type: ignore[attr-defined]
        height = float(entity.dxf.get("height", _DEFAULT_CHAR_HEIGHT))  # type: ignore[attr-defined]
    else:
        text = entity.text or ""  # type: ignore[attr-defined]
        insert = entity.dxf.insert  # type: ignore[attr-defined]
        height = float(entity.dxf.get("char_height", _DEFAULT_CHAR_HEIGHT))  # type: ignore[attr-defined]
    return text, insert, height


def _estimate_bounding_box(text: str, insert: object, height: float) -> BoundingBox:
    """テキストのバウンディングボックスを文字数・高さから推定する（FR-021）。

    全角・半角を区別して幅を計算する。

    Args:
        text: テキスト内容。
        insert: 挿入点（ezdxf Vectorオブジェクト）。
        height: 文字高さ（DXFユニット）。

    Returns:
        BoundingBox: 推定バウンディングボックス。
    """
    width = _text_width(text, height)
    x = float(insert.x)  # type: ignore[attr-defined]
    y = float(insert.y)  # type: ignore[attr-defined]
    return BoundingBox(
        min_x=x,
        min_y=y - height * 0.2,
        max_x=x + width,
        max_y=y + height,
    )


def _text_width(text: str, height: float) -> float:
    """全角・半角を区別してテキスト幅を推定する。

    Args:
        text: テキスト内容。
        height: 文字高さ（DXFユニット）。

    Returns:
        float: 推定テキスト幅。
    """
    width = 0.0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        width += height if eaw in ("W", "F") else height * _CHAR_WIDTH_FACTOR
    return width


def _is_dimension_text(text: str) -> bool:
    """テキストが寸法数値（正規表現）かどうかを判定する。

    Args:
        text: 判定するテキスト文字列。

    Returns:
        bool: 寸法数値パターンにマッチする場合True。
    """
    return bool(_DIMENSION_PATTERN.match(text.strip()))


def _strip_mtext_codes(text: str) -> str:
    """MTEXTの書式コードを除去し、段落区切り（\\P）を改行に変換する。

    Args:
        text: MTEXTの生テキスト文字列。

    Returns:
        str: 書式コードを除去した文字列。
    """
    clean = re.sub(r"\\[A-Za-z][^;]*;", "", text)
    clean = re.sub(r"\{[^{}]*\}", clean, clean)
    clean = clean.replace("\\P", "\n")
    return clean.strip()
