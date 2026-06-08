"""メインオーケストレーションパイプライン。"""
import logging
import sys
from pathlib import Path

from dxf_extractor.config import AppConfig
from dxf_extractor.models.drawing import DXFDrawing, Metadata
from dxf_extractor.parsers.dxf_reader import get_dxf_version, read_dxf
from dxf_extractor.parsers.shape_extractor import extract_shapes

logger = logging.getLogger(__name__)

_SIZE_WARNING_BYTES = 5 * 1024 * 1024  # 5MB


def run_pipeline(
    dxf_path: Path, config: AppConfig, llm_enabled: bool | None = None
) -> DXFDrawing:
    """DXFファイルを処理して構造化情報を返す。

    Args:
        dxf_path: 処理するDXFファイルのパス。
        config: アプリケーション設定。
        llm_enabled: 抽出フェーズのLLM使用有無の上書き（US4）。Noneで
            ``config.llm.enabled`` に従う（後方互換）。

    Returns:
        DXFDrawing: 抽出した全情報を含むデータオブジェクト。

    Raises:
        ValueError: DXFファイルの読み込みまたはバージョン検証に失敗した場合。
        FileNotFoundError: ファイルが存在しない場合。
    """
    use_llm = config.llm.enabled if llm_enabled is None else llm_enabled
    _check_file_size(dxf_path)

    doc = read_dxf(dxf_path, config.dxf)
    version = get_dxf_version(doc)
    logger.info("DXF読み込み中: %s (%s)", dxf_path.name, version)

    # エンティティ供給を一元化（既定はモデルスペースのみ・INSERT非展開＝従来挙動）。
    from dxf_extractor.parsers.entity_source import iter_entities
    entities = iter_entities(doc, config.extraction.entity_source)

    shapes = _safe_extract("形状", lambda: extract_shapes(entities))

    from dxf_extractor.parsers.dimension_extractor import extract_dimensions
    dimensions = _safe_extract("寸法", lambda: extract_dimensions(entities))

    from dxf_extractor.parsers.text_extractor import extract_texts
    notes, text_dimensions = _safe_extract("テキスト", lambda: extract_texts(entities))

    from dxf_extractor.parsers.table_extractor import extract_tables
    tables = _safe_extract("表", lambda: extract_tables(entities))

    from dxf_extractor.parsers.layer_extractor import extract_layers
    layers = _safe_extract("レイヤ", lambda: extract_layers(doc, config.extraction.keywords, entities))

    from dxf_extractor.analyzers.tolerance_parser import parse_tolerances
    tolerances = _safe_extract("公差", lambda: parse_tolerances(notes, dimensions))

    from dxf_extractor.analyzers.duplicate_resolver import resolve_duplicates
    text_dimensions = _safe_extract(
        "テキスト寸法重複",
        lambda: resolve_duplicates(text_dimensions, dimensions, config.extraction.text_dimension.duplicate_threshold),
    )

    # スケール推定（US3）。既定（auto_scale=False）では係数1.0でブロック検出は現行同一。
    from dxf_extractor.analyzers.scale_estimator import estimate_scale
    scale_ctx = estimate_scale(doc, shapes, config.structurize.scale)

    from dxf_extractor.analyzers.block_detector import detect_blocks
    blocks = _safe_extract(
        "ブロック検出",
        lambda: detect_blocks(
            shapes, dimensions, notes, config.extraction.clustering, scale_ctx.factor
        ),
    )

    from dxf_extractor.analyzers.frame_detector import detect_frames
    frame_indices = _safe_extract("図枠検出", lambda: detect_frames(blocks, shapes, layers))

    from dxf_extractor.analyzers.metadata_extractor import extract_metadata
    metadata_fields = _safe_extract(
        "メタ情報",
        lambda: extract_metadata(blocks, shapes, notes, frame_indices, config.extraction.keywords),
    )

    if use_llm:
        try:
            from dxf_extractor.llm.labeler import label_with_llm
            blocks, layers = label_with_llm(blocks, layers, config.llm)
        except Exception as e:
            logger.warning("LLM応答エラー: ルールベース処理にフォールバックしました — %s", e)

    # auto_scale 有効時のみスケール文脈を出力に記録する（既定は None でゴールデン不変／FR-304）。
    scale_context = scale_ctx if config.structurize.scale.auto_scale else None
    metadata = Metadata(dxf_version=version, scale_context=scale_context, **metadata_fields)

    logger.info(
        "エンティティ抽出: 形状=%d, 寸法=%d, テキスト=%d",
        len(shapes),
        len(dimensions),
        len(notes),
    )
    logger.info("ブロック検出: %dブロック", len(blocks))

    return DXFDrawing(
        metadata=metadata,
        blocks=blocks,
        shapes=shapes,
        dimensions=dimensions,
        text_dimensions=text_dimensions,
        tolerances=tolerances,
        tables=tables,
        notes=notes,
        layers=layers,
    )


def _safe_extract(category: str, fn: object):
    """カテゴリ別エラー隔離付きで抽出関数を実行する（FR-017）。

    Args:
        category: エラーメッセージ用カテゴリ名。
        fn: 実行する抽出関数（引数なし callable）。

    Returns:
        抽出関数の戻り値。エラー時は空リストまたは空のデフォルト値。
    """
    try:
        return fn()  # type: ignore[operator]
    except Exception as e:
        logger.warning("[WARN] %s抽出でエラーが発生しました: %s。他のカテゴリの結果は出力されます。", category, e)
        # テキスト抽出は(notes, text_dims)のタプルを返すため空タプルを返す
        if category == "テキスト":
            return [], []
        return []


def _check_file_size(path: Path) -> None:
    """5MB超のファイルにパフォーマンス警告を出力する（SC-001）。

    Args:
        path: 確認するファイルパス。
    """
    try:
        size = path.stat().st_size
        if size > _SIZE_WARNING_BYTES:
            mb = size / (1024 * 1024)
            logger.warning(
                "[WARN] 大容量ファイル (%.1fMB) が入力されました。5MB超のファイルはパフォーマンス保証外です。",
                mb,
            )
    except OSError:
        pass
