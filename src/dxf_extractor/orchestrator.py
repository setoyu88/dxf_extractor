"""DXF→抽出→構造化を連結するオーケストレータ。

抽出フェーズ(a)と体系化フェーズ(b)を独立した関数（``run_extract`` /
``run_structurize``）に分割し、連続実行（``run_all``）はそれらを合成する
（US1 / FR-001〜003 / FR-018）。LLM使用の有無はフェーズごとに
``config.effective_extraction_llm`` / ``config.effective_structurize_llm`` で解決する
（US4 / FR-009〜011）。体系化ルールは ``config.structurize.rules_config`` の外部JSONで
制御できる（US3 / FR-014）。
"""
import logging
from dataclasses import dataclass
from pathlib import Path

from dxf_extractor.associators.rule_loader import load_rule_steps
from dxf_extractor.config import AppConfig
from dxf_extractor.models.association import StructuredDrawing
from dxf_extractor.models.drawing import DXFDrawing
from dxf_extractor.pipeline import run_pipeline
from dxf_extractor.structurize_pipeline import StructurizePipeline

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """オーケストレーションの結果をまとめるコンテナ。

    Attributes:
        drawing: 抽出結果（中間成果物）。
        structured: 体系化結果（最終成果物）。
        mode: 実行モード表示用文字列（"カテゴリA" / "カテゴリA+B" など）。
    """

    drawing: DXFDrawing
    structured: StructuredDrawing
    mode: str


def _mode_string(extract_llm: bool, struct_llm: bool) -> str:
    """フェーズ別の実効LLM有無から処理モード表示文字列を生成する。

    両フェーズが一致する場合は従来表記（カテゴリA / カテゴリA+B）を維持する。
    """
    if extract_llm == struct_llm:
        return "カテゴリA+B" if extract_llm else "カテゴリA"
    ex = "A+B" if extract_llm else "A"
    st = "A+B" if struct_llm else "A"
    return f"抽出=カテゴリ{ex} / 体系化=カテゴリ{st}"


def run_extract(
    dxf_path: Path, config: AppConfig, llm_override: bool | None = None
) -> DXFDrawing:
    """抽出フェーズ(a): DXFファイルから抽出データを生成する。

    Args:
        dxf_path: 入力DXFファイルパス。
        config: アプリケーション設定。
        llm_override: CLI ``--llm/--no-llm`` の上書き。Noneで設定に従う。

    Returns:
        DXFDrawing: 抽出結果。

    Raises:
        ValueError: DXFファイルの読み込みまたはバージョン検証に失敗した場合。
        FileNotFoundError: ファイルが存在しない場合。
        OSError: ファイルアクセスに失敗した場合。
    """
    extract_llm = config.effective_extraction_llm(llm_override)
    return run_pipeline(dxf_path, config, llm_enabled=extract_llm)


def run_structurize(
    drawing: DXFDrawing,
    config: AppConfig,
    quiet: bool = False,
    llm_override: bool | None = None,
) -> StructuredDrawing:
    """体系化フェーズ(b): 抽出データから体系化データを生成する。

    Args:
        drawing: 抽出結果（フェーズ(a)の出力）。
        config: アプリケーション設定。
        quiet: Trueの場合、ルール単位の進捗表示を抑制する。
        llm_override: CLI ``--llm/--no-llm`` の上書き。Noneで設定に従う。

    Returns:
        StructuredDrawing: 体系化結果。

    Raises:
        RuleConfigError: ルール設定JSONが不正な場合。
    """
    # スケール係数を関連付けしきい値へ適用する（US3=005 / FR-301）。
    # 既定（auto_scale=False）では scale_context が None のため従来挙動を維持する。
    structurize_config = config.structurize
    scale_ctx = drawing.metadata.scale_context
    if scale_ctx is not None and scale_ctx.factor != 1.0:
        structurize_config = config.structurize.model_copy(deep=True)
        structurize_config.tolerances.delta *= scale_ctx.factor
        structurize_config.tolerances.d_threshold *= scale_ctx.factor

    # 体系化フェーズのLLM可否を解決（LLM無効時は llm_config=None でカテゴリAのみ）。
    struct_llm = config.effective_structurize_llm(llm_override)
    llm_config = config.llm if struct_llm else None

    # 外部JSONからルールステップ列を取得（未指定なら既定＝現行ルール構成）。
    rule_steps = load_rule_steps(config.structurize.rules_config)

    pipeline = StructurizePipeline(rule_steps)
    structured = pipeline.run(drawing, structurize_config, llm_config, quiet=quiet)
    logger.info("体系化完了: 関連付け=%d件", len(structured.associations))
    return structured


def run_all(
    dxf_path: Path,
    config: AppConfig,
    quiet: bool = False,
    llm_override: bool | None = None,
) -> OrchestrationResult:
    """連続実行 (a)+(b): DXFファイルから抽出・構造化までを一気通貫で実行する。

    Args:
        dxf_path: 入力DXFファイルパス。
        config: アプリケーション設定。
        quiet: Trueの場合、構造化処理のルール単位の進捗表示を抑制する。
        llm_override: CLI ``--llm/--no-llm`` の上書き。Noneで設定に従う。

    Returns:
        OrchestrationResult: 抽出結果・構造化結果・実行モードを含む結果。

    Raises:
        ValueError: DXFファイルの読み込みまたはバージョン検証に失敗した場合。
        FileNotFoundError: ファイルが存在しない場合。
        OSError: ファイルアクセスに失敗した場合。
        RuleConfigError: ルール設定JSONが不正な場合。
    """
    drawing = run_extract(dxf_path, config, llm_override)
    structured = run_structurize(drawing, config, quiet=quiet, llm_override=llm_override)

    extract_llm = config.effective_extraction_llm(llm_override)
    struct_llm = config.effective_structurize_llm(llm_override)
    mode = _mode_string(extract_llm, struct_llm)
    logger.info("体系化完了: モード=%s, 関連付け=%d件", mode, len(structured.associations))

    return OrchestrationResult(drawing=drawing, structured=structured, mode=mode)


# 後方互換: 旧 orchestrator.run（連続実行）のエイリアス。
def run(dxf_path: Path, config: AppConfig, quiet: bool = False) -> OrchestrationResult:
    """連続実行 (a)+(b) の後方互換エイリアス（``run_all`` と同等）。

    Args:
        dxf_path: 入力DXFファイルパス。
        config: アプリケーション設定。
        quiet: Trueの場合、ルール単位の進捗表示を抑制する。

    Returns:
        OrchestrationResult: 抽出結果・構造化結果・実行モードを含む結果。
    """
    return run_all(dxf_path, config, quiet=quiet)
