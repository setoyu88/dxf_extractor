"""DXFファイルをPDFに変換するスクリプト。

ezdxfのDrawingアドオン（PyMuPdfバックエンド）を使用してDXFをPDFに変換する。
"""

import sys
from pathlib import Path

import click
import ezdxf
from ezdxf import recover
from ezdxf.addons.drawing import Frontend, RenderContext, layout, pymupdf


def _render_pdf(backend: pymupdf.PyMuPdfBackend, page: layout.Page, output_layers: bool) -> bytes:
    """PDFバイト列を生成する。レイヤーOCG付きで試み、失敗したらOCGなしで再試行する。

    Args:
        backend: PyMuPdfバックエンド。
        page: ページ定義。
        output_layers: レイヤーOCGを出力に含めるかどうか。

    Returns:
        PDFのバイト列。
    """
    settings = layout.Settings(output_layers=output_layers)
    try:
        return backend.get_pdf_bytes(page, settings=settings)
    except TypeError:
        if output_layers:
            # レイヤー名に非ASCII文字が含まれる場合にPyMuPDFがTypeErrorを送出する
            click.echo("警告: レイヤーOCGの生成に失敗しました。レイヤー情報なしで変換します。", err=True)
            settings = layout.Settings(output_layers=False)
            return backend.get_pdf_bytes(page, settings=settings)
        raise


def convert_dxf_to_pdf(
    input_path: Path,
    output_path: Path,
    page_width_mm: float,
    page_height_mm: float,
    margin_mm: float,
    output_layers: bool = True,
) -> None:
    """DXFファイルをPDFに変換する。

    Args:
        input_path: 入力DXFファイルパス。
        output_path: 出力PDFファイルパス。
        page_width_mm: ページ幅（mm）。
        page_height_mm: ページ高さ（mm）。
        margin_mm: 余白（mm）。
        output_layers: レイヤーOCGをPDFに含めるかどうか。

    Raises:
        IOError: DXFファイルの読み込みに失敗した場合。
        ezdxf.DXFStructureError: DXFファイルの構造が不正な場合。
    """
    try:
        doc, auditor = recover.readfile(str(input_path))
    except IOError as e:
        raise IOError(f"DXFファイルの読み込みに失敗しました: {e}") from e
    except ezdxf.DXFStructureError as e:
        raise ezdxf.DXFStructureError(f"DXFファイルの構造が不正です: {e}") from e

    if auditor.has_errors:
        click.echo(f"警告: DXFファイルに {len(auditor.errors)} 件のエラーがあります。", err=True)
        for error in auditor.errors[:10]:
            click.echo(f"  - [{error.code}] {error.message}", err=True)
        if len(auditor.errors) > 10:
            click.echo(f"  ... 他 {len(auditor.errors) - 10} 件", err=True)

    msp = doc.modelspace()
    context = RenderContext(doc)
    backend = pymupdf.PyMuPdfBackend()
    Frontend(context, backend).draw_layout(msp)

    page = layout.Page(
        page_width_mm,
        page_height_mm,
        layout.Units.mm,
        margins=layout.Margins.all(margin_mm),
    )
    pdf_bytes = _render_pdf(backend, page, output_layers)
    output_path.write_bytes(pdf_bytes)


@click.command()
@click.argument("input_dxf", type=click.Path(exists=True, path_type=Path))
@click.argument("output_pdf", type=click.Path(path_type=Path), required=False)
@click.option("--width", default=297.0, show_default=True, help="ページ幅（mm）。デフォルトはA4横。")
@click.option("--height", default=210.0, show_default=True, help="ページ高さ（mm）。デフォルトはA4横。")
@click.option("--margin", default=10.0, show_default=True, help="余白（mm）。")
@click.option("--no-layers", is_flag=True, default=False, help="PDFのレイヤーOCGを無効化する。")
def main(
    input_dxf: Path,
    output_pdf: Path | None,
    width: float,
    height: float,
    margin: float,
    no_layers: bool,
) -> None:
    """DXFファイルをPDFに変換する。

    INPUT_DXF: 入力DXFファイルのパス。
    OUTPUT_PDF: 出力PDFファイルのパス（省略時は入力ファイルと同名の.pdfを生成）。
    """
    if output_pdf is None:
        output_pdf = input_dxf.with_suffix(".pdf")

    click.echo(f"変換中: {input_dxf} -> {output_pdf}")

    try:
        convert_dxf_to_pdf(input_dxf, output_pdf, width, height, margin, output_layers=not no_layers)
        click.echo(f"変換完了: {output_pdf}")
    except IOError as e:
        click.echo(f"エラー: {e}", err=True)
        sys.exit(1)
    except ezdxf.DXFStructureError as e:
        click.echo(f"エラー: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
