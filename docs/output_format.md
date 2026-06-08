# 出力形式（構造化データ → ファイル）

担当: `src/dxf_extractor/cli.py`（書き出し）＋ `serializers/`（変換）。

## 1. 生成されるファイル（サブコマンド別）

| サブコマンド | ファイル | 担当 | 条件 |
|--------------|----------|------|------|
| `extract`（(a)） | `<名前>.json`（抽出JSON） | `json_serializer.write_json` | 常に生成 |
| `structurize`（(b)） | `<名前>_structured.json` | `StructuredDrawing.model_dump_json` | 常に生成 |
| `structurize`（(b)） | `<名前>_structured.md` | `serializers/md_serializer.py` | 常に生成 |
| `run`（(a)+(b)） | `<名前>_structured.json` / `.md` | 上に同じ | 常に生成 |
| `run`（(a)+(b)） | `<名前>.json`（抽出JSON） | `json_serializer.write_json` | `--save-intermediate` 指定時のみ |

- `<名前>` は入力ファイルの拡張子なしファイル名。出力先は `--output-dir`、未指定時は入力と同じ場所。
- 抽出JSON（`extract` 出力）は `structurize` の入力。スキーマは `DXFDrawing` と同一で、`json_serializer.load_drawing` でロスレスに読み戻す（`associations` は含まない）。

## 2. 構造化JSON スキーマ

抽出データ（`DXFDrawing`）の全フィールドに `associations` を加えたもの（`models/association.py: StructuredDrawing`）。

```jsonc
{
  "metadata": {
    "dxf_version": "R2018",
    "title": "部品図", "drawing_number": "DWG-001", "revision": "A", "scale": "1:1",
    "created_by": null, "designed_by": null, "checked_by": null, "approved_by": null,
    "material": null
  },
  "blocks": [          // 論理ブロック（DBSCANクラスタ）。type: part_view/sub_view/table/frame/notes
    { "id": "block_001", "type": "part_view", "bounding_box": {...},
      "shape_ids": [...], "dimension_ids": [...], "note_ids": [...], "llm_labeled": false }
  ],
  "shapes": [          // 幾何形状。geometry は line/circle/arc/polyline/other のいずれか
    { "id": "shape_001", "layer": "外形線", "bounding_box": {...}, "geometry": {...} }
  ],
  "dimensions": [      // DIMENSIONエンティティ。dim_type: linear/diameter/radial/angular/ordinate
    { "id": "dim_001", "dim_type": "linear", "direction": "x", "value": 100.0,
      "position": {...}, "extension_point_1": {...}, "extension_point_2": {...} }
  ],
  "text_dimensions": [ // テキストで記載された寸法。is_duplicate で記号寸法との重複を表す
    { "id": "tdim_001", "value": 5.0, "position": {...}, "is_duplicate": false }
  ],
  "tolerances": [      // 公差。tol_type: grade/bilateral/symmetric
    { "id": "tol_001", "tol_type": "symmetric", "upper": 0.05, "lower": -0.05 }
  ],
  "tables": [          // 表・部品表（行×セル）
    { "id": "table_001", "rows": [ { "index": 0, "cells": [ { "row":0,"col":0,"text":"番号" } ] } ] }
  ],
  "notes": [           // 注記テキスト（TEXT/MTEXT）
    { "id": "note_001", "text": "...", "position": {...}, "entity_type": "MTEXT" }
  ],
  "layers": [          // レイヤ情報
    { "name": "外形線", "entity_types": ["LINE"], "entity_count": 12, "purpose": "外形線" }
  ],
  "associations": [    // ★構造化JSONのみ。抽出JSONには含まれない
    { "rule": "1-1", "source_id": "dim_001", "target_ids": ["shape_002"],
      "confidence": 1.0, "extracted_value": null, "llm_augmented": false }
  ]
}
```

`associations` の各レコードの意味は [構造化ルール詳細](./structurization_rules.md) を参照。

### 2-1. 汎用化拡張で追加される任意フィールド（005、オプトイン）

以下は対応する設定を有効にしたときだけ付与される。**既定（無効）では出力に現れず**、従来スキーマと一致する（`models/shape.py: OmitNoneMixin` が `None` 時に省略）。

| フィールド | 付与位置 | 条件 | 意味 |
|------------|----------|------|------|
| `sheet` | `shapes[]` / `dimensions[]` / `notes[]` / `tables[]` | `extraction.entity_source.process_paperspace: true` | 帰属シート名（`Model` / レイアウト名） |
| `source_block` | `shapes[].geometry`（OtherGeometryのみ） | `extraction.entity_source.expand_inserts: true` | INSERT展開要素の由来ブロック名 |
| `scale_context` | `metadata` | `structurize.scale.auto_scale: true` | `{ "unit", "factor", "source" }`（採用単位・係数・推定根拠 insunits/bbox/default） |

## 3. Markdownレポートの構成

`md_serializer.py` が `StructuredDrawing` を人間可読のレポートにする。先頭にヘッダ
（`# 図面体系化レポート: <入力名>` と `生成日時 / 処理モード`）、続いて11セクション。

| # | セクション | 主な内容 |
|---|------------|----------|
| 1 | 標題欄 | 図番・タイトル・尺度・材料・作成/照査/承認者（metadata） |
| 2 | 部品表 | テーブル構造・番号列・サイズ列 |
| 3 | 部品詳細 | 部品番号ごとの形状・寸法のまとめ |
| 4 | 断面関係 | 断面記号と断面図ブロックの対応 |
| 5 | 視図グループ | 投影関係でグループ化した視図 |
| 6 | 注記・改定情報 | 注記エリア・改定履歴 |
| 7 | 形状一覧 | 全形状の種別・位置・サイズ |
| 8 | 寸法一覧 | 記号寸法・テキスト寸法 |
| 9 | 許容差一覧 | 公差 |
| 10 | 論理ブロック一覧 | ブロックの種別・包含エンティティ |
| 11 | 処理サマリー | 件数・処理モード（カテゴリA / A+B） |

- 「処理モード」は `OrchestrationResult.mode`（LLM無効=`カテゴリA`、有効=`カテゴリA+B`）。
- 「生成日時」は実行時刻のため**非決定的**。退行比較ではこの2行を除外して本文を比較する。

## 4. 終了コード（FR-016）

| コード | 意味 |
|--------|------|
| 0 | 正常終了 |
| 1 | 一般エラー（出力書き込み失敗・処理中エラー） |
| 2 | 入力フォーマット不正（DXF読込/バージョン検証失敗、引数不正） |
| 3 | 設定ファイル不正 |

実装は `cli_support.py`（定数）と `cli.py`（例外→コード対応）。すべてのエラーメッセージは日本語。

---

関連: [抽出フェーズ詳細](./extraction_details.md) / [構造化ルール詳細](./structurization_rules.md)
