"""DXFファイル読み込みとバージョン検証。"""
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing

from dxf_extractor.config import DxfConfig

_VERSION_ORDER = [
    "R12", "R13", "R14", "R2000", "R2004", "R2007", "R2010", "R2013", "R2018",
]

_ACAD_TO_VERSION: dict[str, str] = {
    "AC1009": "R12",
    "AC1012": "R13",
    "AC1014": "R14",
    "AC1015": "R2000",
    "AC1018": "R2004",
    "AC1021": "R2007",
    "AC1024": "R2010",
    "AC1027": "R2013",
    "AC1032": "R2018",
}


def _version_index(version: str) -> int:
    """バージョン文字列をインデックスに変換する。"""
    try:
        return _VERSION_ORDER.index(version)
    except ValueError:
        return -1


def read_dxf(path: Path, dxf_config: DxfConfig | None = None) -> Drawing:
    """DXFファイルを読み込み、バージョンを検証して返す。

    Args:
        path: 読み込むDXFファイルのパス。
        dxf_config: DXF設定（サポートバージョン範囲など）。

    Returns:
        Drawing: ezdxf Drawing オブジェクト。

    Raises:
        FileNotFoundError: ファイルが存在しない場合。
        ValueError: DXFバージョンがサポート範囲外の場合、またはファイルが不正な場合。
    """
    if not path.exists():
        raise FileNotFoundError(f"DXFファイルが見つかりません: {path}")

    try:
        doc = ezdxf.readfile(str(path))
    except ezdxf.DXFError as e:
        raise ValueError(f"DXFファイルの読み込みに失敗しました: {path} — {e}") from e
    except Exception as e:
        raise ValueError(f"ファイルの読み込み中にエラーが発生しました: {path} — {e}") from e

    if dxf_config is not None:
        _validate_version(doc, dxf_config)

    return doc


def _validate_version(doc: Drawing, dxf_config: DxfConfig) -> None:
    """DXFバージョンがサポート範囲内かどうか検証する。

    Args:
        doc: ezdxf Drawing オブジェクト。
        dxf_config: バージョン範囲を含むDXF設定。

    Raises:
        ValueError: バージョンがサポート範囲外の場合。
    """
    acad_version = doc.dxfversion
    detected = _ACAD_TO_VERSION.get(acad_version, acad_version)

    min_ver = dxf_config.supported_versions.min
    max_ver = dxf_config.supported_versions.max
    min_idx = _version_index(min_ver)
    max_idx = _version_index(max_ver)
    detected_idx = _version_index(detected)

    if detected_idx == -1 or detected_idx < min_idx or detected_idx > max_idx:
        raise ValueError(
            f"DXFバージョン非対応: {acad_version} ({detected}) はサポート対象外です。"
            f"対応範囲: {min_ver} ({_acad_code(min_ver)}) 〜 {max_ver} ({_acad_code(max_ver)})"
        )


def _acad_code(version: str) -> str:
    """バージョン文字列をACADコードに変換する。"""
    reverse = {v: k for k, v in _ACAD_TO_VERSION.items()}
    return reverse.get(version, "不明")


def get_dxf_version(doc: Drawing) -> str:
    """DXF Drawingからバージョン文字列を取得する。

    Args:
        doc: ezdxf Drawing オブジェクト。

    Returns:
        str: バージョン文字列（例: "R2018"）。不明な場合はACADコードをそのまま返す。
    """
    return _ACAD_TO_VERSION.get(doc.dxfversion, doc.dxfversion)
