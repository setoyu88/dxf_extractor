"""統合CLIエントリポイント（click）。

DXFファイルの抽出フェーズ(a)と体系化フェーズ(b)を、サブコマンドで個別／連続実行できる
（US1 / US2 / FR-001〜007）。

- ``extract``: (a)のみ。DXF→抽出JSON ``<stem>.json``
- ``structurize``: (b)のみ。抽出JSON→構造化JSON＋Markdown
- ``run``: (a)+(b)連続。DXF→構造化JSON＋Markdown（``--save-intermediate`` で抽出JSONも保存）

サブコマンドを省略した場合は ``config.yaml`` の ``execution.mode`` 既定（既定 ``run``）に
従ってディスパッチする（後方互換: ``dxf-extract <file> --no-llm`` は従来どおり連続実行）。
"""
import logging
from pathlib import Path

import click
from dotenv import load_dotenv
from pydantic import ValidationError

from dxf_extractor import __version__, cli_support, orchestrator
from dxf_extractor.associators.rule_loader import RuleConfigError
from dxf_extractor.config import AppConfig, load_config
from dxf_extractor.serializers.json_serializer import load_drawing, write_json
from dxf_extractor.serializers.md_serializer import MDSerializer

logger = logging.getLogger(__name__)


# ============================================================
# 共通処理（FR-018: 重複排除。各サブコマンドはこれらに委譲する）
# ============================================================
def _common_options(f):
    """全サブコマンド共通のオプションを付与するデコレータ。"""
    f = click.option(
        "--output-dir",
        "output_dir",
        default=None,
        type=click.Path(file_okay=False),
        help="成果物の出力先ディレクトリ（未指定時は入力ファイルと同じ場所）",
    )(f)
    f = click.option(
        "-c", "--config", "config_path", default=None, type=click.Path(path_type=Path), help="設定ファイルパス"
    )(f)
    f = click.option(
        "-l",
        "--log-level",
        "log_level",
        default="normal",
        type=click.Choice(["quiet", "normal", "verbose"], case_sensitive=False),
        help="ログレベル",
    )(f)
    f = click.option(
        "--llm/--no-llm",
        "llm_override",
        default=None,
        help="LLMを有効/無効にする（未指定時はconfig.yamlの設定に従う。対象は当該フェーズ）",
    )(f)
    return f


def _setup_and_config(log_level: str, config_path: Path | None) -> tuple[AppConfig, bool]:
    """ロギング・環境変数・設定読み込みを行い、(設定, quiet) を返す。"""
    cli_support.setup_logging(log_level)
    load_dotenv()
    try:
        config = load_config(config_path)
    except Exception as e:
        cli_support.error_exit(
            f"[ERROR] 設定ファイルの読み込みに失敗しました: {e}", cli_support.EXIT_INVALID_CONFIG
        )
    quiet = log_level.lower() == "quiet"
    return config, quiet


def _mode_label(struct_llm: bool) -> str:
    """体系化フェーズの実効LLMから処理モード表示文字列を返す。"""
    return "カテゴリA+B" if struct_llm else "カテゴリA"


def _write_structured(structured, input_file: Path, out_dir: Path, mode: str) -> tuple[Path, Path]:
    """構造化JSONとMarkdownを書き出す。"""
    _, structured_json, structured_md = cli_support.output_paths(input_file, out_dir)
    try:
        structured_json.write_text(structured.model_dump_json(indent=2), encoding="utf-8")
        md_content = MDSerializer().serialize(structured, source_file=input_file.name, mode=mode)
        structured_md.write_text(md_content, encoding="utf-8")
    except OSError as e:
        cli_support.error_exit(
            f"[ERROR] 出力ファイルの書き込みに失敗しました: {e}", cli_support.EXIT_GENERAL
        )
    return structured_json, structured_md


def _do_extract(
    input_file: Path,
    output_dir: str | None,
    config: AppConfig,
    llm_override: bool | None,
) -> None:
    """抽出フェーズ(a)を実行し、抽出JSONを書き出す。"""
    try:
        drawing = orchestrator.run_extract(input_file, config, llm_override)
    except ValueError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_INVALID_INPUT)
    except OSError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_GENERAL)

    out_dir = cli_support.resolve_output_dir(input_file, output_dir)
    intermediate_json, _, _ = cli_support.output_paths(input_file, out_dir)
    try:
        write_json(drawing, intermediate_json)
    except OSError as e:
        cli_support.error_exit(
            f"[ERROR] 出力ファイルの書き込みに失敗しました: {e}", cli_support.EXIT_GENERAL
        )
    logger.info("抽出完了 → %s", intermediate_json)
    click.echo(f"完了: {intermediate_json}")


def _do_structurize(
    input_file: Path,
    output_dir: str | None,
    config: AppConfig,
    llm_override: bool | None,
    quiet: bool,
) -> None:
    """体系化フェーズ(b)を実行し、構造化JSON＋Markdownを書き出す。"""
    # 抽出JSON（フェーズ(a)出力）を読み戻す。不正は入力フォーマット不正として扱う。
    try:
        drawing = load_drawing(input_file)
    except (ValidationError, ValueError) as e:
        cli_support.error_exit(
            f"[ERROR] 抽出JSONの読み込みに失敗しました（フォーマット不正）: {e}",
            cli_support.EXIT_INVALID_INPUT,
        )
    except OSError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_GENERAL)

    try:
        structured = orchestrator.run_structurize(
            drawing, config, quiet=quiet, llm_override=llm_override
        )
    except RuleConfigError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_INVALID_CONFIG)

    mode = _mode_label(config.effective_structurize_llm(llm_override))
    out_dir = cli_support.resolve_output_dir(input_file, output_dir)
    structured_json, structured_md = _write_structured(structured, input_file, out_dir, mode)
    logger.info("処理完了 → %s, %s", structured_json, structured_md)
    if not quiet:
        click.echo(f"完了: {structured_json}, {structured_md}")


def _do_run(
    input_file: Path,
    output_dir: str | None,
    config: AppConfig,
    llm_override: bool | None,
    save_intermediate: bool,
    quiet: bool,
) -> None:
    """連続実行 (a)+(b) を行い、構造化JSON＋Markdown（＋任意で抽出JSON）を書き出す。"""
    try:
        result = orchestrator.run_all(input_file, config, quiet=quiet, llm_override=llm_override)
    except ValueError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_INVALID_INPUT)
    except RuleConfigError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_INVALID_CONFIG)
    except OSError as e:
        cli_support.error_exit(f"[ERROR] {e}", cli_support.EXIT_GENERAL)

    out_dir = cli_support.resolve_output_dir(input_file, output_dir)
    intermediate_json, _, _ = cli_support.output_paths(input_file, out_dir)
    if save_intermediate:
        try:
            write_json(result.drawing, intermediate_json)
        except OSError as e:
            cli_support.error_exit(
                f"[ERROR] 出力ファイルの書き込みに失敗しました: {e}", cli_support.EXIT_GENERAL
            )

    structured_json, structured_md = _write_structured(
        result.structured, input_file, out_dir, result.mode
    )
    logger.info("処理完了 → %s, %s", structured_json, structured_md)
    if not quiet:
        click.echo(f"完了: {structured_json}, {structured_md}")


# ============================================================
# CLI: サブコマンド未指定時に既定コマンドへフォールバックするグループ
# ============================================================
class _DefaultGroup(click.Group):
    """先頭引数がサブコマンドでない場合に既定コマンド（_auto）へフォールバックする。"""

    _DEFAULT_CMD = "_auto"

    def resolve_command(self, ctx, args):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            # 先頭がファイルパス等でサブコマンドに一致しない → 既定コマンドへ委譲
            return super().resolve_command(ctx, [self._DEFAULT_CMD, *args])


@click.group(cls=_DefaultGroup, invoke_without_command=False)
@click.version_option(version=__version__, prog_name="dxf-extract")
def main() -> None:
    """DXFファイルから抽出・体系化を行う（extract / structurize / run）。"""


@main.command(name="extract")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@_common_options
def extract_cmd(
    input_file: Path,
    output_dir: str | None,
    config_path: Path | None,
    log_level: str,
    llm_override: bool | None,
) -> None:
    """抽出フェーズ(a): DXFから抽出JSON（<stem>.json）を生成する。"""
    config, _ = _setup_and_config(log_level, config_path)
    _do_extract(input_file, output_dir, config, llm_override)


@main.command(name="structurize")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@_common_options
def structurize_cmd(
    input_file: Path,
    output_dir: str | None,
    config_path: Path | None,
    log_level: str,
    llm_override: bool | None,
) -> None:
    """体系化フェーズ(b): 抽出JSONから構造化JSON＋Markdownを生成する。"""
    config, quiet = _setup_and_config(log_level, config_path)
    _do_structurize(input_file, output_dir, config, llm_override, quiet)


@main.command(name="run")
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@_common_options
@click.option(
    "--save-intermediate",
    "save_intermediate",
    is_flag=True,
    default=False,
    help="中間成果物（抽出JSON <stem>.json）も保存する",
)
def run_cmd(
    input_file: Path,
    output_dir: str | None,
    config_path: Path | None,
    log_level: str,
    llm_override: bool | None,
    save_intermediate: bool,
) -> None:
    """連続実行 (a)+(b): DXFから構造化JSON＋Markdownを生成する。"""
    config, quiet = _setup_and_config(log_level, config_path)
    _do_run(input_file, output_dir, config, llm_override, save_intermediate, quiet)


@main.command(name="_auto", hidden=True)
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@_common_options
@click.option("--save-intermediate", "save_intermediate", is_flag=True, default=False)
def auto_cmd(
    input_file: Path,
    output_dir: str | None,
    config_path: Path | None,
    log_level: str,
    llm_override: bool | None,
    save_intermediate: bool,
) -> None:
    """サブコマンド未指定時のディスパッチ用（config.yaml の execution.mode に従う）。"""
    config, quiet = _setup_and_config(log_level, config_path)
    mode = config.execution.mode
    if mode == "extract":
        _do_extract(input_file, output_dir, config, llm_override)
    elif mode == "structurize":
        _do_structurize(input_file, output_dir, config, llm_override, quiet)
    else:
        _do_run(input_file, output_dir, config, llm_override, save_intermediate, quiet)
