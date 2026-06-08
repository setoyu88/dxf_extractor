"""MDシリアライザ: 体系化済み図面をMarkdownレポートに変換する。"""
import math
import re
from datetime import datetime

from dxf_extractor.models.association import AssociationResult, StructuredDrawing
from dxf_extractor.models.block import BlockType
from dxf_extractor.models.shape import BoundingBox, Point2D
from dxf_extractor.models.table import Table, TableRow

# ============================================================
# ユーティリティ関数（T003）
# ============================================================

_NOTE_HEADER_PATTERN = re.compile(r"^Note[s]?$", re.IGNORECASE)


def _fmt_coord(pos: Point2D | None) -> str:
    """Point2D を '(x.x, y.y)' 形式で返す。Noneは '—'。"""
    if pos is None:
        return "—"
    return f"({pos.x:.1f}, {pos.y:.1f})"


def _fmt_size(bb: BoundingBox) -> str:
    """BoundingBox から '幅.x × 高さ.y' 形式を返す。"""
    w = bb.max_x - bb.min_x
    h = bb.max_y - bb.min_y
    return f"{w:.1f} × {h:.1f}"


def _fmt_wh(bb: BoundingBox) -> str:
    """BoundingBox から '(w.x, h.y)' 形式を返す。"""
    w = bb.max_x - bb.min_x
    h = bb.max_y - bb.min_y
    return f"({w:.1f}, {h:.1f})"


def _center_coord(bb: BoundingBox) -> str:
    """BoundingBox の中心座標を '(x.x, y.y)' 形式で返す。"""
    cx = (bb.min_x + bb.max_x) / 2
    cy = (bb.min_y + bb.max_y) / 2
    return f"({cx:.1f}, {cy:.1f})"


def _format_optional(value: str | None) -> str:
    return value if value else "—"


# ============================================================
# ルール説明辞書（T004）
# ============================================================

_RULE_DESCRIPTIONS: dict[str, str] = {
    "1-1": "寸法線↔形状マッチング",
    "1-2": "寸法線↔形状マッチング（延長点）",
    "1-3": "寸法線↔形状マッチング（LLM補完）",
    "2-1": "テキスト寸法分類",
    "2-2": "テキスト寸法重複除去",
    "3-0": "テーブル境界検出",
    "3-1": "テーブルセル構造解析",
    "3-2": "テーブルヘッダー識別",
    "3-3": "テーブル種別分類",
    "4-1": "断面記号識別",
    "4-2": "断面記号↔断面図関連付け",
    "4-3": "断面関係LLM補完",
    "5-1": "注記↔形状近傍関連付け",
    "5-2": "注記↔形状テキスト照合",
    "5-3": "注記↔形状LLM補完",
    "6-1": "投影視図グループ化",
    "6-2": "視図グループLLM補完",
    "7-1": "ハッチング↔形状包含判定",
    "7-2": "ハッチング↔形状近傍関連付け",
    "7-3": "ハッチングLLM補完",
    "8-1": "標題欄フィールド抽出",
    "8-2": "標題欄LLM抽出",
    "8-3": "標題欄フォールバック抽出",
    "9-1": "Noteエリア識別",
    "9-2": "改定情報抽出",
    "10-1": "部品番号テキスト識別",
    "10-2": "部品番号↔LogicalBlock関連付け",
    "10-3": "部品番号↔部品表行関連付け",
}


# ============================================================
# シリアライザ
# ============================================================

class MDSerializer:
    """StructuredDrawing を Markdown レポートに変換する。"""

    def serialize(
        self,
        structured: StructuredDrawing,
        source_file: str,
        mode: str,
    ) -> str:
        """体系化済み図面を Markdown レポートに変換する。

        Args:
            structured: 体系化済み図面。
            source_file: 入力ファイル名（レポートのヘッダーに記載）。
            mode: 処理モード（例: "カテゴリA", "カテゴリA+B"）。

        Returns:
            str: Markdown レポート文字列。
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sections = [
            f"# 図面体系化レポート: {source_file}",
            f"生成日時: {now}  処理モード: {mode}",
            "",
            self._title_block_section(structured),       # ## 1. 標題欄
            self._parts_table_section(structured),        # ## 2. 部品表
            self._part_details_section(structured),       # ## 3. 部品詳細
            self._cross_section_section(structured),      # ## 4. 断面関係
            self._view_group_section(structured),         # ## 5. 視図グループ
            self._notes_revision_section(structured),     # ## 6. 注記・改定情報
            self._shapes_section(structured),             # ## 7. 形状一覧
            self._dimensions_section(structured),         # ## 8. 寸法一覧
            self._tolerances_section(structured),         # ## 9. 許容差一覧
            self._blocks_section(structured),             # ## 10. 論理ブロック一覧
            self._summary_section(structured, mode),      # ## 11. 処理サマリー
        ]
        return "\n".join(sections)

    def _title_block_section(self, structured: StructuredDrawing) -> str:
        meta = structured.metadata
        lines = [
            "## 1. 標題欄",
            "",
            "| 項目 | 値 |",
            "|------|-----|",
            f"| 図面タイトル | {_format_optional(meta.title)} |",
            f"| 図面番号 | {_format_optional(meta.drawing_number)} |",
            f"| 縮尺 | {_format_optional(meta.scale)} |",
            f"| 作成者 | {_format_optional(meta.created_by)} |",
            f"| 設計者 | {_format_optional(meta.designed_by)} |",
            f"| 照査者 | {_format_optional(meta.checked_by)} |",
            f"| 承認者 | {_format_optional(meta.approved_by)} |",
            f"| 材料 | {_format_optional(meta.material)} |",
            "",
        ]
        return "\n".join(lines)

    def _parts_table_section(self, structured: StructuredDrawing) -> str:
        """部品表セクション: Rule10-3または直接テーブル検索で部品表を出力。位置・サイズ列付き。"""
        rule10_3_assocs = [a for a in structured.associations if a.rule == "10-3"]
        lines = ["## 2. 部品表", ""]

        if rule10_3_assocs:
            # rule 10-3 経由: テーブル特定・サイズ列付き出力
            seen: set[str] = set()
            table_ids: list[str] = []
            for assoc in rule10_3_assocs:
                for tid in assoc.target_ids:
                    table_id = tid.split(":")[0]
                    if table_id not in seen:
                        seen.add(table_id)
                        table_ids.append(table_id)

            table_map_t = {t.id: t for t in structured.tables}

            # テーブル行インデックス → source_id マッピング
            table_row_to_src: dict[str, str] = {}
            for assoc in rule10_3_assocs:
                for tid in assoc.target_ids:
                    parts = tid.split(":")
                    if len(parts) == 3:
                        table_row_to_src[f"{parts[0]}:{parts[2]}"] = assoc.source_id

            for table_id in table_ids:
                table = table_map_t.get(table_id)
                if table is None or len(table.rows) < 1:
                    continue

                header_cells = table.rows[0].cells
                col_names = [cell.text for cell in header_cells] + ["位置", "サイズ"]
                data_rows = table.rows[1:]

                lines.append(f"抽出件数: {len(data_rows)} 件")
                lines.append("")
                lines.append("| " + " | ".join(col_names) + " |")
                lines.append("| " + " | ".join(["---"] * len(col_names)) + " |")

                for row in data_rows:
                    cell_texts = [cell.text for cell in row.cells]
                    src_id = table_row_to_src.get(f"{table_id}:{row.index}")
                    info = self._find_shape_info_for_part(src_id, structured) if src_id else None
                    if info:
                        cx, cy, w, h = info
                        pos_str = f"({cx:.1f}, {cy:.1f})"
                        size_str = f"({w:.1f}, {h:.1f})"
                    else:
                        pos_str = "—"
                        size_str = "—"
                    cell_texts.extend([pos_str, size_str])
                    lines.append("| " + " | ".join(cell_texts) + " |")

            lines.append("")
            return "\n".join(lines)

        # フォールバック: "番号" ヘッダーを持つテーブルを直接検索
        parts_table, header_row = self._find_parts_table(structured)
        if parts_table is None or header_row is None:
            lines.append("（部品表の関連付けなし）")
            lines.append("")
            return "\n".join(lines)

        header_cells = header_row.cells
        header_positions = [c.position for c in header_cells if c.position]
        col_names = [c.text for c in header_cells] + ["位置", "サイズ"]

        if header_positions:
            # ヘッダーセルのX範囲でデータ行をフィルタリング
            h_x_min = min(p.x for p in header_positions)
            h_x_max = max(p.x for p in header_positions)
            X_TOL = 20.0
            data_rows_filtered = []
            for row in parts_table.rows:
                if row.index <= header_row.index:
                    continue
                rel_cells = [
                    c for c in row.cells
                    if c.position and (h_x_min - X_TOL) <= c.position.x <= (h_x_max + X_TOL)
                ]
                if len(rel_cells) == len(header_cells):
                    data_rows_filtered.append(rel_cells)
        else:
            # ヘッダーセルに位置情報がない場合: セル数が一致する後続行を使用
            data_rows_filtered = [
                row.cells
                for row in parts_table.rows
                if row.index > header_row.index and len(row.cells) == len(header_cells)
            ]

        # rule 10-1: 番号値 → source_id マッピング
        part_num_to_src: dict[str, str] = {}
        for a in structured.associations:
            if a.rule == "10-1":
                for tid in a.target_ids:
                    if tid.startswith("part_number:"):
                        num = tid.split(":")[1]
                        part_num_to_src[num] = a.source_id

        lines.append(f"抽出件数: {len(data_rows_filtered)} 件")
        lines.append("")
        lines.append("| " + " | ".join(col_names) + " |")
        lines.append("| " + " | ".join(["---"] * len(col_names)) + " |")

        for cells in data_rows_filtered:
            cell_texts = [c.text for c in cells]
            num_text = cells[0].text.strip() if cells else ""
            src_id = part_num_to_src.get(num_text)
            info = self._find_shape_info_for_part(src_id, structured) if src_id else None
            if info:
                cx, cy, w, h = info
                pos_str = f"({cx:.1f}, {cy:.1f})"
                size_str = f"({w:.1f}, {h:.1f})"
            else:
                pos_str = "—"
                size_str = "—"
            cell_texts.extend([pos_str, size_str])
            lines.append("| " + " | ".join(cell_texts) + " |")

        lines.append("")
        return "\n".join(lines)

    def _find_parts_table(
        self, structured: StructuredDrawing
    ) -> tuple[Table | None, TableRow | None]:
        """'番号' セルを含むヘッダー行を持つテーブルを返す。"""
        for table in structured.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip() == "番号":
                        return table, row
        return None, None

    def _find_shape_info_for_part(
        self,
        source_id: str,
        structured: StructuredDrawing,
    ) -> tuple[float, float, float, float] | None:
        """部品番号 source_id に対応する図面内形状の (cx, cy, w, h) を返す。

        Args:
            source_id: rule10-1 の source_id（TextDimension ID）。
            structured: 体系化済み図面。

        Returns:
            (cx, cy, w, h) または None（対応形状が見つからない場合）。
        """
        if not structured.shapes:
            return None

        tdim_map = {td.id: td for td in structured.text_dimensions}
        tdim = tdim_map.get(source_id)
        if tdim is None:
            return None
        tx, ty = tdim.position.x, tdim.position.y

        def bbox_center(bb: BoundingBox) -> tuple[float, float]:
            return ((bb.min_x + bb.max_x) / 2, (bb.min_y + bb.max_y) / 2)

        def dist(cx: float, cy: float) -> float:
            return math.sqrt((cx - tx) ** 2 + (cy - ty) ** 2)

        nearest_shape = min(structured.shapes, key=lambda s: dist(*bbox_center(s.bounding_box)))
        ncx, ncy = bbox_center(nearest_shape.bounding_box)

        if nearest_shape.geometry.type == "POLYLINE":
            bb = nearest_shape.bounding_box
            return (ncx, ncy, bb.max_x - bb.min_x, bb.max_y - bb.min_y)

        # LINE → 近傍 part_view ブロックの合成 bbox
        BLOCK_SEARCH_RADIUS = 50.0
        nearby = [
            b for b in structured.blocks
            if b.type == BlockType.part_view
            and dist(*bbox_center(b.bounding_box)) <= BLOCK_SEARCH_RADIUS
        ]
        if not nearby:
            return None

        combined_min_x = min(b.bounding_box.min_x for b in nearby)
        combined_max_x = max(b.bounding_box.max_x for b in nearby)
        combined_min_y = min(b.bounding_box.min_y for b in nearby)
        combined_max_y = max(b.bounding_box.max_y for b in nearby)
        cx = (combined_min_x + combined_max_x) / 2
        cy = (combined_min_y + combined_max_y) / 2
        w = combined_max_x - combined_min_x
        h = combined_max_y - combined_min_y
        return (cx, cy, w, h)

    def _part_details_section(self, structured: StructuredDrawing) -> str:
        """部品詳細セクション（T012）: Rule10-2/10-3をsource_idで統合し品名・型番・サイズ・中心座標を出力。"""
        lines = ["## 3. 部品詳細", ""]
        lines.append("> 注意: サイズはLogicalBlockのbounding_boxから算出。寸法線を含む場合があります。")
        lines.append("")

        rule10_3_assocs = [a for a in structured.associations if a.rule == "10-3"]
        if not rule10_3_assocs:
            lines.append("（部品詳細なし）")
            lines.append("")
            return "\n".join(lines)

        # source_id → 最高confidence rule10-2
        rule10_2_assocs = [a for a in structured.associations if a.rule == "10-2"]
        r10_2_best: dict[str, AssociationResult] = {}
        for assoc in rule10_2_assocs:
            if assoc.source_id not in r10_2_best or assoc.confidence > r10_2_best[assoc.source_id].confidence:
                r10_2_best[assoc.source_id] = assoc

        table_map = {t.id: t for t in structured.tables}
        block_map = {b.id: b for b in structured.blocks}

        # テーブルのheaderから列名を取得
        col_names: list[str] = []
        for assoc in rule10_3_assocs:
            for tid in assoc.target_ids:
                table_id = tid.split(":")[0]
                table = table_map.get(table_id)
                if table and table.rows:
                    col_names = [cell.text for cell in table.rows[0].cells]
                    break
            if col_names:
                break

        # 登場順に source_id を収集（重複除去）
        seen: set[str] = set()
        source_ids: list[str] = []
        r10_3_by_source: dict[str, AssociationResult] = {}
        for assoc in rule10_3_assocs:
            if assoc.source_id not in seen:
                seen.add(assoc.source_id)
                source_ids.append(assoc.source_id)
            if assoc.source_id not in r10_3_by_source:
                r10_3_by_source[assoc.source_id] = assoc

        lines.append(f"抽出件数: {len(source_ids)} 件")
        lines.append("")

        header_cols = col_names + ["サイズ（幅×高さ）", "中心位置"]
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(header_cols)) + " |")

        for source_id in source_ids:
            assoc = r10_3_by_source[source_id]
            cell_texts: list[str] = ["—"] * len(col_names)
            for tid in assoc.target_ids:
                parts = tid.split(":")
                if len(parts) >= 3:
                    table_id = parts[0]
                    try:
                        row_idx = int(parts[2])
                    except ValueError:
                        continue
                    table = table_map.get(table_id)
                    if table:
                        for row in table.rows:
                            if row.index == row_idx:
                                cell_texts = [cell.text for cell in row.cells]
                                break
                        break

            size_str = "—"
            center_str = "—"
            if source_id in r10_2_best:
                best_assoc = r10_2_best[source_id]
                for block_id in best_assoc.target_ids:
                    block = block_map.get(block_id)
                    if block:
                        size_str = _fmt_size(block.bounding_box)
                        center_str = _center_coord(block.bounding_box)
                        break

            row_data = cell_texts + [size_str, center_str]
            lines.append("| " + " | ".join(row_data) + " |")

        lines.append("")
        return "\n".join(lines)

    def _cross_section_section(self, structured: StructuredDrawing) -> str:
        rule42_assocs = [a for a in structured.associations if a.rule == "4-2"]
        lines = ["## 4. 断面関係", ""]

        if not rule42_assocs:
            lines.append("（断面関係の関連付けなし）")
            lines.append("")
            return "\n".join(lines)

        lines.extend([
            "| 断面記号（注記ID） | 断面図ブロック |",
            "|------------------|---------------|",
        ])
        for assoc in rule42_assocs:
            targets = ", ".join(assoc.target_ids)
            lines.append(f"| {assoc.source_id} | {targets} |")
        lines.append("")
        return "\n".join(lines)

    def _view_group_section(self, structured: StructuredDrawing) -> str:
        rule61_assocs = [a for a in structured.associations if a.rule == "6-1"]
        lines = ["## 5. 視図グループ", ""]

        if not rule61_assocs:
            lines.append("（投影関係のある視図グループなし）")
            lines.append("")
            return "\n".join(lines)

        for assoc in rule61_assocs:
            targets = ", ".join(assoc.target_ids)
            lines.append(f"- {assoc.source_id} → {targets}")
        lines.append("")
        return "\n".join(lines)

    def _notes_revision_section(self, structured: StructuredDrawing) -> str:
        """注記・改定情報セクション: Note枠内の全ノートを空間的に抽出して出力。"""
        lines = ["## 6. 注記・改定情報", ""]

        rule92_assocs = [a for a in structured.associations if a.rule == "9-2"]
        rule91_note_assocs = [
            a for a in structured.associations
            if a.rule == "9-1" and a.source_id.startswith("note_")
        ]

        if not rule92_assocs and not rule91_note_assocs:
            lines.append("（改定情報なし）")
            lines.append("")
            return "\n".join(lines)

        note_map = {n.id: n for n in structured.notes}

        # アンカーノード（rule 9-2）とヘッダーノード（rule 9-1 note）を収集
        anchor_notes = [note_map[a.source_id] for a in rule92_assocs if a.source_id in note_map]
        header_notes = [note_map[a.source_id] for a in rule91_note_assocs if a.source_id in note_map]

        if not anchor_notes and not header_notes:
            lines.append("（改定情報なし）")
            lines.append("")
            return "\n".join(lines)

        # Note枠の検索範囲をアンカー・ヘッダーのbounding_boxから算出
        ref_notes = anchor_notes if anchor_notes else header_notes
        x_min = min(n.bounding_box.min_x for n in ref_notes)
        x_max = max(n.bounding_box.max_x for n in ref_notes)
        y_min = min(n.bounding_box.min_y for n in ref_notes)
        y_max = max(n.bounding_box.max_y for n in ref_notes)

        if header_notes:
            x_min = min(x_min, min(n.bounding_box.min_x for n in header_notes))
            x_max = max(x_max, max(n.bounding_box.max_x for n in header_notes))
            y_min = min(y_min, min(n.bounding_box.min_y for n in header_notes))
            y_max = max(y_max, max(n.bounding_box.max_y for n in header_notes))

        MARGIN_X = 5.0
        MARGIN_Y = 50.0
        search_x_min = x_min - MARGIN_X
        search_x_max = x_max + MARGIN_X
        search_y_min = y_min - MARGIN_Y
        search_y_max = y_max + MARGIN_Y

        # 枠内の全ノートを抽出（ヘッダーノートと "Note/Notes" ラベルを除外）
        header_ids = {n.id for n in header_notes}
        area_notes = []
        for note in structured.notes:
            if note.id in header_ids:
                continue
            if _NOTE_HEADER_PATTERN.match(note.text.strip()):
                continue
            p = note.position
            if search_x_min <= p.x <= search_x_max and search_y_min <= p.y <= search_y_max:
                area_notes.append(note)

        # 上から下・左から右の順でソート
        area_notes.sort(key=lambda n: (-n.position.y, n.position.x))

        output_lines: list[str] = []
        for note in area_notes:
            coord = _fmt_coord(note.position)
            for text_line in note.text.replace("\\P", "\n").split("\n"):
                text_line = text_line.strip()
                if text_line:
                    output_lines.append(f"- {text_line}  {coord}")

        lines.append(f"抽出件数: {len(output_lines)} 件")
        lines.append("")
        if output_lines:
            lines.extend(output_lines)
        else:
            lines.append("（改定情報なし）")
        lines.append("")
        return "\n".join(lines)

    def _shapes_section(self, structured: StructuredDrawing) -> str:
        """形状一覧セクション（T019）: shapes全件をテーブル形式で出力。"""
        shapes = structured.shapes
        lines = ["## 7. 形状一覧", "", f"抽出件数: {len(shapes)} 件", ""]

        if not shapes:
            return "\n".join(lines)

        lines.extend([
            "| ID | 種別 | レイヤー | 中心位置 |",
            "|----|------|---------|---------|",
        ])
        for shape in shapes:
            geo_type = shape.geometry.type
            center = _center_coord(shape.bounding_box)
            lines.append(f"| {shape.id} | {geo_type} | {shape.layer} | {center} |")
        lines.append("")
        return "\n".join(lines)

    def _dimensions_section(self, structured: StructuredDrawing) -> str:
        """寸法一覧セクション（T020）: dimensions/text_dimensions全件をサブセクションで出力。"""
        dims = structured.dimensions
        tdims = structured.text_dimensions
        lines = ["## 8. 寸法一覧", ""]

        lines.extend(["### 寸法エンティティ", "", f"抽出件数: {len(dims)} 件", ""])
        if dims:
            lines.extend([
                "| ID | 種別 | テキスト | 位置 |",
                "|----|------|---------|------|",
            ])
            for dim in dims:
                pos = _fmt_coord(dim.position)
                lines.append(f"| {dim.id} | {dim.dim_type.value} | {dim.text} | {pos} |")
        lines.append("")

        lines.extend(["### テキスト寸法", "", f"抽出件数: {len(tdims)} 件", ""])
        if tdims:
            lines.extend([
                "| ID | テキスト | 位置 |",
                "|----|---------|------|",
            ])
            for tdim in tdims:
                pos = _fmt_coord(tdim.position)
                lines.append(f"| {tdim.id} | {tdim.text} | {pos} |")
        lines.append("")
        return "\n".join(lines)

    def _tolerances_section(self, structured: StructuredDrawing) -> str:
        """許容差一覧セクション（T021）: tolerances全件をテーブル形式で出力。"""
        tolerances = structured.tolerances
        lines = ["## 9. 許容差一覧", "", f"抽出件数: {len(tolerances)} 件", ""]

        if not tolerances:
            return "\n".join(lines)

        lines.extend([
            "| ID | 種別 | テキスト | 位置 |",
            "|----|------|---------|------|",
        ])
        for tol in tolerances:
            pos = _fmt_coord(tol.position)
            lines.append(f"| {tol.id} | {tol.tol_type.value} | {tol.text} | {pos} |")
        lines.append("")
        return "\n".join(lines)

    def _blocks_section(self, structured: StructuredDrawing) -> str:
        """論理ブロック一覧セクション（T022）: blocks全件をテーブル形式で出力。"""
        blocks = structured.blocks
        lines = ["## 10. 論理ブロック一覧", "", f"抽出件数: {len(blocks)} 件", ""]

        if not blocks:
            return "\n".join(lines)

        lines.extend([
            "| ID | 種別 | 名前 | サイズ（幅×高さ） | 中心位置 |",
            "|----|------|------|-----------------|---------|",
        ])
        for block in blocks:
            name = block.name if block.name else "—"
            size = _fmt_size(block.bounding_box)
            center = _center_coord(block.bounding_box)
            lines.append(f"| {block.id} | {block.type.value} | {name} | {size} | {center} |")
        lines.append("")
        return "\n".join(lines)

    def _summary_section(self, structured: StructuredDrawing, mode: str) -> str:
        """処理サマリーセクション（T014）: ルール別件数に説明文を付記。"""
        total = len(structured.associations)
        llm_count = sum(1 for a in structured.associations if a.llm_augmented)
        llm_err_count = sum(1 for a in structured.associations if a.llm_error)

        rule_counts: dict[str, int] = {}
        for assoc in structured.associations:
            rule_counts[assoc.rule] = rule_counts.get(assoc.rule, 0) + 1

        lines = [
            "## 11. 処理サマリー",
            "",
            f"- 処理モード: {mode}",
            f"- 関連付け総件数: {total}",
            f"- LLM補完使用: {llm_count} 件",
            f"- LLMエラー（フォールバック）: {llm_err_count} 件",
            "",
            "### ルール別件数",
            "",
        ]
        for rule_id in sorted(rule_counts.keys()):
            desc = _RULE_DESCRIPTIONS.get(rule_id, "説明なし")
            lines.append(f"- ルール {rule_id}（{desc}）: {rule_counts[rule_id]} 件")
        lines.append("")
        return "\n".join(lines)
