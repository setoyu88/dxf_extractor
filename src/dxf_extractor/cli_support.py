"""統合CLIの共通ユーティリティ。

ロギング設定・出力パス解決・エラー終了処理を一元化し、
抽出CLIと構造化CLIで重複していた処理を統合する（FR-011）。
"""
import logging
import sys
from pathlib import Path
from typing import NoReturn

import click

# 終了コード規約（FR-016 / contracts/cli.md）
EXIT_OK = 0
"""正常終了。"""
EXIT_GENERAL = 1
"""一般エラー（読込・書込・処理中エラー）。"""
EXIT_INVALID_INPUT = 2
"""入力フォーマット不正。"""
EXIT_INVALID_CONFIG = 3
"""設定ファイル不正。"""

_LOG_LEVELS = {
    "quiet": logging.ERROR,
    "normal": logging.INFO,
    "verbose": logging.DEBUG,
}

_LOG_FORMAT = "[%(levelname)s] %(message)s"


def setup_logging(level_name: str) -> None:
    """stderrへのロギングを設定する。

    Args:
        level_name: ログレベル名（quiet/normal/verbose）。
    """
    level = _LOG_LEVELS.get(level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def resolve_output_dir(input_path: Path, output_dir: str | None) -> Path:
    """出力先ディレクトリを解決する。

    Args:
        input_path: 入力DXFファイルパス。
        output_dir: 出力先ディレクトリ。Noneの場合は入力ファイルと同じディレクトリ。

    Returns:
        Path: 解決した出力先ディレクトリ（存在しない場合は作成済み）。
    """
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = input_path.parent
    return out_dir


def output_paths(input_path: Path, out_dir: Path) -> tuple[Path, Path, Path]:
    """成果物の出力パスを既存の命名規則で生成する。

    Args:
        input_path: 入力DXFファイルパス。
        out_dir: 出力先ディレクトリ。

    Returns:
        tuple[Path, Path, Path]: (抽出JSON, 構造化JSON, Markdownレポート) のパス。
            抽出JSONは `<stem>.json`、構造化JSONは `<stem>_structured.json`、
            Markdownは `<stem>_structured.md`。
    """
    stem = input_path.stem
    intermediate_json = out_dir / f"{stem}.json"
    structured_json = out_dir / f"{stem}_structured.json"
    structured_md = out_dir / f"{stem}_structured.md"
    return intermediate_json, structured_json, structured_md


def error_exit(message: str, code: int) -> NoReturn:
    """日本語エラーメッセージをstderrに出力して終了する。

    Args:
        message: エラーメッセージ（日本語）。
        code: 終了コード（EXIT_* 定数）。
    """
    click.echo(message, err=True)
    sys.exit(code)
