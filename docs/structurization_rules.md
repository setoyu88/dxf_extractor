# 構造化ルール詳細（抽出データ → 構造化データ）

担当: `src/dxf_extractor/structurize_pipeline.py` の `StructurizePipeline.run()`。
抽出データ（`DXFDrawing`）の要素どうしの**関係**を、10種類のルール（`associators/rule1`〜`rule10`）で
順番に判定し、`AssociationResult`（関連付け）の列として `StructuredDrawing.associations` に蓄積する。

## 関連付けの共通形（AssociationResult）

各ルールは次の形のレコードを生成する（`models/association.py`）。

| フィールド | 意味 |
|------------|------|
| `rule` | 適用したサブルール番号（例 `"1-1"`, `"8-2"`） |
| `source_id` | 関連付け元エンティティID（例 `dim_001`, `note_003`） |
| `target_ids` | 関連付け先ID群。実体ID（例 `shape_002`）または意味ラベル（例 `section:A`, `metadata.scale`, `col:0:番号`） |
| `confidence` | 信頼スコア（0.0〜1.0） |
| `extracted_value` | 抽出した値（標題欄の値・改定内容など。任意） |
| `llm_augmented` / `llm_error` | LLMで補完されたか／LLM呼び出しが失敗してフォールバックしたか |

## 共通の仕組み（base.py）

- 全ルールは `AssociatorBase` を継承し、`associate()` に判定ロジックを実装する（Template Methodパターン）。
- `run()` が `associate()` の結果を **信頼スコアでフィルタ**する（`confidence >= structurize.confidence_threshold`、既定 `0.0` のため全件採用）。
- 1ルールが例外を投げても、パイプラインが警告を出して**次のルールへ継続**する。

## 実行順序（Decision 7）

順序には依存関係がある（先に表・標題欄・断面を確定 → 寸法/視図/部品番号 → 注記）。

| 実行順 | ルール | 内容 | カテゴリ |
|--------|--------|------|----------|
| 1 | Rule3 | テーブル構造化 | A（3-1のみA/B） |
| 2 | Rule8 | 標題欄構造化 | A（8-2のみA/B） |
| 3 | Rule9 | 改定情報抽出 | A（9-2のみA/B） |
| 4 | Rule4 | 断面表示関連付け | A |
| 5 | Rule7 | ハッチング関連付け | A（7-2のみA/B） |
| 6 | Rule1 | 寸法↔形状マッチング | A |
| 7 | Rule6 | 視図間投影関係 | A |
| 8 | Rule10 | 部品番号紐づけ | A |
| 9 | Rule2 | テキスト寸法分類 | A |
| 10 | Rule5 | 注記↔形状対応 | A（5-3のみA/B） |

最後に `_apply_metadata()` が、`8-2`/`8-3`/`9-2` などの `extracted_value` を
`StructuredDrawing.metadata` に反映する（後述）。

---

## Rule1: 寸法↔形状マッチング（カテゴリA）

各寸法について次を判定する。

- **1-1 線形寸法の端点マッチング**: linear寸法の引出点1/2が、形状（LINE/POLYLINE）の端点から
  `tolerances.delta`（既定2.0）以内にある形状を対応付け（confidence 1.0）。
- **1-2 径/直径寸法と円のマッチング**: diameter/radial寸法の位置が円の半径内にある `CircleGeometry` を対応付け（1.0）。
- **1-3 寸法のブロック帰属**: 寸法の引出点がブロックbbox内にあれば、そのブロックに帰属（1.0）。

## Rule2: テキスト寸法分類（カテゴリA）

- **2-1 レイヤによる分類**: テキスト寸法のレイヤ名に `dim/寸法/scale` 等 → `寸法線`、`table/部品` 等 → `テーブル番号`（1.0）。
- **2-2 テーブル番号との位置マッチング**: テキスト寸法位置がテーブルbbox内なら、そのテーブルに対応付け（1.0）。

## Rule3: テーブル構造化（カテゴリA / 3-1のみA/B）

各テーブルについて:

- **3-0 テーブル境界識別**: テーブル位置を含むブロックを対応付け（1.0）。
- **3-1 ヘッダー行の特定**: `番号/品名/型番/数量/材料…` 等のキーワードを含む行をヘッダーとする
  （無ければ先頭行）。キーワードは `extraction.keywords.table_headers`（既定=現行と同一）で追加/置換可能（005）。
  **LLM有効時はLLMでヘッダー特定の精度を上げる**（`row:idx` をフォールバック）。
- **3-2 同一行のセル集約**: `delta_y_ratio`（既定0.5）を記録（行判定の基準）。
- **3-3 列名対応付け**: ヘッダー行のセルを列順に並べ `col:i:列名` を生成。

## Rule4: 断面表示関連付け（カテゴリA）

注記から断面記号（`A-A`、`A`、`断面A-A`）を抽出し:

- **4-1 断面識別子の抽出**: 断面レイヤまたはパターン一致で `section:A` を生成（1.0）。
  断面レイヤキーワードは `extraction.keywords.section`、断面記号パターンは
  `structurize.profile.section_symbol_pattern`（既定=`A-A`／単一英字）で変更でき、数字断面等に対応できる（005）。
- **4-2 断面図ブロックの紐づけ**: 名前に断面記号を含むブロックを対応付け（1.0）。無ければ最近傍ブロック（0.7）。
- **4-3 切断線方向**: 現状は `direction:unknown` を固定生成（0.8）→ [残課題](./extensibility_and_issues.md)。

## Rule5: 注記↔形状対応（カテゴリA / 5-3のみA/B）

各注記について:

- **5-1 レイヤ大分類**: レイヤ名から `category:annotation/cross/table` を判定（1.0）。
- **5-2 LEADER（引き出し線）対応**: 注記位置がLEADER形状のbboxから `d_threshold`（既定5.0）以内なら対応付け（1.0）。
- **5-3 近接テキストと形状の対応**: 注記近傍（`d_threshold`以内）の非LEADER形状のうち最近傍を採用（1.0）。
  **LLM有効時は候補から最適な形状をLLMが判定**（最近傍をフォールバック）。

## Rule6: 視図間投影関係（カテゴリA）

`part_view` ブロックが2つ以上あるとき:

- **6-1 座標軸による投影対応**: x範囲が重なりy方向に離れる（正面図↔上面図）/ y範囲が重なりx方向に離れる
  （正面図↔側面図）ブロック対を対応付け（1.0）。
- **6-2 共通寸法による同定**: 同じ寸法IDを共有するブロック対を対応付け（1.0）。

> 注: ブロック種別 `part_view` は抽出段階の既定値。LLMでの再分類が無くても本ルールは機能する。

## Rule7: ハッチング関連付け（カテゴリA / 7-2のみA/B）

各HATCH形状について:

- **7-1 境界形状の特定**: ハッチbboxに内包される閉形状（閉ポリライン/円）を境界として対応付け（1.0）。
  見つからなければ `no_boundary`（0.5）。
- **7-2 LEADER対応**: 同一ブロック内のLEADERを対応付け。**LLM有効時はLLMで対応LEADERを特定**（候補をフォールバック）。
- **7-3 断面表示対応**: レイヤ名に `cross` を含めば `cross_section` を対応付け（1.0）。

## Rule8: 標題欄構造化（カテゴリA / 8-2のみA/B）

- **8-1 標題欄領域の特定**: `table` 型ブロックのうち**最下端**のものを標題欄とする（`metadata.title_block`）。
- **8-2 ラベル-値ペア認識**: 標題欄内の注記から `作成/設計/照査/承認/材料/尺度/Title/図面番号…` のラベルを検出し、
  対応する値注記（**水平＝同一y行で右隣、垂直＝同一x列で下方**）を `extracted_value` として紐づけ（1.0）。
  **LLM有効時はラベルに対応する値テキストをLLMが返す**（カテゴリA結果をフォールバック）。
- **8-3 NTS識別**: テキストが `NTS` の注記を `metadata.scale = "NTS"` に対応付け（1.0）。

> **重要（LLM依存）**: 8-1 は `table` 型ブロックを前提とするが、ブロック種別は **LLMラベリングでのみ**
> `table` になる。LLM無効時は `table` ブロックが存在しないため、標題欄ノートの収集は
> **図面下端20%エリアへのフォールバック**で行われる（`_get_title_block_notes`）。
>
> フォールバック領域は `structurize.profile.title_block_region`（`bottom`/`top`/`top_right`/`bottom_right`/`auto`、既定 `bottom`）
> と `title_block_ratio`（既定0.2）で変更でき、右上標題欄等に対応できる（005）。ラベル語彙は
> `extraction.keywords.title_block_labels` で多言語追加できる。

## Rule9: 改定情報抽出（カテゴリA / 9-2のみA/B）

- **9-1 Noteエリアの識別**: `notes` 型ブロック、または `Note(s)` ヘッダーテキストを `metadata.notes_area` に対応付け（1.0）。
- **9-2 改定情報の抽出**: `REV/改定/revision` を含む注記から改定内容を抽出し `metadata.revision` に格納（1.0）。
  改定キーワードは `extraction.keywords.revision`（既定=現行と同一）で追加/置換可能（005）。
  **LLM有効時はLLMが改定内容を整形抽出**（正規表現抽出をフォールバック）。

## Rule10: 部品番号紐づけ（カテゴリA）

部品番号レイヤ（`part_no/text` 等）かつ整数値かつ非重複のテキスト寸法について:

> `structurize.profile.part_number_style` を `balloon`/`both` にすると、レイヤ制約を外して整数テキストを
> 部品番号候補に含め、円囲みバルーン番号（INSERT展開と併用）を拾える（005）。既定 `integer_text` は現行挙動。

- **10-1 部品番号の識別**: `part_number:N` を生成（1.0）。
- **10-2 部品ビューとの関連付け**: 番号位置が `part_view` ブロックbbox（`delta` マージン）内なら対応付け（1.0）。
  無ければ最近傍ブロック（0.7）。
- **10-3 部品表行との関連付け**: 部品表の「番号」列を特定し、同じ番号値を持つ行を `table:row:idx` に対応付け（1.0）。

---

## メタデータへの反映（_apply_metadata）

ルール適用後、`target_ids` が `metadata.*` を指し `extracted_value` を持つ関連付けを
`StructuredDrawing.metadata` に書き込む。

- 対象フィールド: `title / drawing_number / scale / created_by / designed_by / checked_by / approved_by / material / revision`。
- 既存値（DXF属性由来）がある場合は基本的に**上書きしない**。
- `revision` は複数あれば改行で追記。
- `scale` は `NTS` より実数尺度を優先。

## 信頼スコアの一覧（既定）

| confidence | 使用箇所 |
|------------|----------|
| 1.0 | ほとんどの確定的な関連付け |
| 0.8 | Rule4-3（切断線方向 unknown） |
| 0.7 | Rule4-2 / Rule10-2 の最近傍フォールバック |
| 0.5 | Rule7-1（境界なし）、LLM呼び出し失敗時のフォールバック |

`structurize.confidence_threshold`（既定0.0）を上げると、低スコアの関連付けを除外できる。

---

関連: [LLM利用の全容](./llm_usage.md) / [出力形式](./output_format.md) / [拡張性と残課題](./extensibility_and_issues.md)
