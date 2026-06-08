"""公差文字列の正規表現パース（FR-007）。"""
import re

from dxf_extractor.models.dimension import Dimension
from dxf_extractor.models.note import Note
from dxf_extractor.models.shape import Point2D
from dxf_extractor.models.tolerance import Tolerance, ToleranceType

_SYMMETRIC = re.compile(r"[±＋－](\d+\.?\d*)")
_SYMMETRIC_ASCII = re.compile(r"[+\-]?(\d+\.?\d*)\s*/\s*[+\-]?(\d+\.?\d*)")
_BILATERAL = re.compile(r"\+(\d+\.?\d*)\s*/\s*-(\d+\.?\d*)")
_GRADE = re.compile(r"([A-Z]\d+)/([a-z]\d+)")
_SYMMETRIC_SIMPLE = re.compile(r"±\s*(\d+\.?\d*)")


def parse_tolerances(notes: list[Note], dimensions: list[Dimension]) -> list[Tolerance]:
    """注記テキストと寸法テキストから公差情報を抽出する（FR-007）。

    Args:
        notes: 注記テキストリスト。
        dimensions: 記号寸法リスト（toleranceフィールド付与も行う）。

    Returns:
        list[Tolerance]: 抽出した公差リスト。
    """
    tolerances: list[Tolerance] = []
    counter = 1

    for note in notes:
        extracted = _extract_from_text(note.text, note.position, note.layer, counter)
        for t in extracted:
            tolerances.append(t)
            counter += 1

    return tolerances


def _extract_from_text(text: str, position: Point2D, layer: str, start_counter: int) -> list[Tolerance]:
    """テキスト文字列から公差パターンを検出してToleranceリストを返す。

    Args:
        text: 対象テキスト。
        position: テキスト位置。
        layer: レイヤ名。
        start_counter: ID採番開始値。

    Returns:
        list[Tolerance]: 検出した公差リスト。
    """
    tolerances: list[Tolerance] = []
    counter = start_counter

    for m in _GRADE.finditer(text):
        tolerances.append(
            Tolerance(
                id=f"tol_{counter:03d}",
                tol_type=ToleranceType.grade,
                text=m.group(0),
                grade=m.group(1),
                fit=m.group(2),
                position=position,
                layer=layer,
            )
        )
        counter += 1

    for m in _BILATERAL.finditer(text):
        upper = float(m.group(1))
        lower = -float(m.group(2))
        tolerances.append(
            Tolerance(
                id=f"tol_{counter:03d}",
                tol_type=ToleranceType.bilateral,
                text=m.group(0),
                upper=upper,
                lower=lower,
                position=position,
                layer=layer,
            )
        )
        counter += 1

    for m in _SYMMETRIC_SIMPLE.finditer(text):
        val = float(m.group(1))
        tolerances.append(
            Tolerance(
                id=f"tol_{counter:03d}",
                tol_type=ToleranceType.symmetric,
                text=m.group(0),
                upper=val,
                lower=-val,
                position=position,
                layer=layer,
            )
        )
        counter += 1

    return tolerances


def parse_tolerance_text(text: str, position: Point2D, layer: str, tol_id: str) -> Tolerance | None:
    """単一テキストから最初の公差パターンを抽出する。

    Args:
        text: 公差テキスト文字列。
        position: テキスト位置。
        layer: レイヤ名。
        tol_id: 付与するID。

    Returns:
        Tolerance | None: 抽出した公差。パターン不一致の場合はNone。
    """
    m = _GRADE.search(text)
    if m:
        return Tolerance(
            id=tol_id,
            tol_type=ToleranceType.grade,
            text=m.group(0),
            grade=m.group(1),
            fit=m.group(2),
            position=position,
            layer=layer,
        )

    m = _BILATERAL.search(text)
    if m:
        upper = float(m.group(1))
        lower = -float(m.group(2))
        return Tolerance(
            id=tol_id,
            tol_type=ToleranceType.bilateral,
            text=m.group(0),
            upper=upper,
            lower=lower,
            position=position,
            layer=layer,
        )

    m = _SYMMETRIC_SIMPLE.search(text)
    if m:
        val = float(m.group(1))
        return Tolerance(
            id=tol_id,
            tol_type=ToleranceType.symmetric,
            text=m.group(0),
            upper=val,
            lower=-val,
            position=position,
            layer=layer,
        )

    return None
