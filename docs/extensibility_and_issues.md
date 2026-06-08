# 拡張性と残課題

本書は、本プログラムを**拡張する方法**と、現時点の**既知の制限・残課題**をまとめる。

## 1. 拡張のしかた

### 1-1. 構造化ルールを設定で切り替える（コード改修なし）

既存ルールの**有効/無効・適用順・パラメータ**は外部JSON設定で変更できる（仕様 `specs/006-split-extract-structurize/`）。

1. ルール設定JSON（契約 `specs/006-split-extract-structurize/contracts/rules_config.schema.json` 準拠）を用意する。
   配列順＝適用順。各要素は `{ "id": "rule3", "enabled": true, "params": {...} }`。
2. `config.yaml` の `structurize.rules_config` にそのパスを指定する。未指定なら現行構成（ゴールデン不変）。

`params` で上書きできるキーは `confidence_threshold` / `tolerances.delta` / `tolerances.d_threshold` /
`tolerances.delta_y_ratio`。不正な設定（未知id・未許可paramsキー・パース不能）は終了コード3（設定不正）。
解決は `associators/registry.py`（id→クラスと既定順）と `associators/rule_loader.py`（読込・検証）が担う。

### 1-1b. 新しい構造化ルールを追加する（コード）

1. `src/dxf_extractor/associators/` に `AssociatorBase` を継承したクラスを作り、`associate()` を実装する。
2. `src/dxf_extractor/associators/registry.py` の `RULE_REGISTRY` と `DEFAULT_ORDER` に**1行ずつ追記**する。

これだけで新ルールがレジストリ既定に組み込まれ、その有効/無効・順序はJSON設定からも制御可能になる。
信頼スコアフィルタ・例外隔離は基底クラスが共通提供する。

### 1-2. 新しい図形・エンティティ種別に対応する

- `parsers/shape_extractor.py` の `_SUPPORTED_TYPES` と `_extract_entity()` に分岐を追加。
- 必要なら `models/shape.py` に新ジオメトリ型を追加。
- 未対応エンティティは現状でも `OtherGeometry` として**捨てずに記録**されるため、まず生属性が残る。

### 1-3. 新しい抽出処理（parser / analyzer）を追加する

- `pipeline.py` の `run_pipeline()` に `_safe_extract("名称", lambda: 新処理())` の形で追加する。
  `_safe_extract` がエラーを隔離するため、新処理の失敗が全体を止めない。

### 1-4. メタ情報フィールド・公差パターンを追加する

- メタ情報: `analyzers/metadata_extractor.py` の正規表現リスト、`associators/rule8_title_block.py` の
  `_LABEL_FIELD_MAP`、`structurize_pipeline.py` の `_METADATA_FIELD_MAP`、`models/drawing.py: Metadata` を更新。
- 公差: `analyzers/tolerance_parser.py` に正規表現を追加。

### 1-5. ルールにLLM補完（カテゴリB）を足す

- ルール内で `llm_config is not None` のときに `associators/llm_helper.py: try_llm_augment()` を呼ぶ。
  カテゴリAの結果を `fallback_target_ids` / `fallback_extracted_value` に渡せば、失敗時も安全に縮退する。

### 1-6. カテゴリC（LLM必須処理）を導入する

現状カテゴリCは**枠組みのみ**。導入する場合の指針:

- LLM無効時は当該処理をスキップし、成果物に「未処理」であることを明示する（サイレントにしない）。
- 退行テストの対象外（LLM必須のため）とし、LLM有効時の専用テストを用意する。
- 分類表（[llm_usage.md](./llm_usage.md)）とこの文書を更新する。

## 1-7. 汎用化拡張（005-drawing-generalization、実装済み・すべてオプトイン）

多様な図面への対応として、以下を **`config.yaml` の設定のみ**で有効化できる（既定はすべて無効＝従来挙動・ゴールデン不変）。

- **多言語キーワード辞書**（`extraction.keywords`）: レイヤ用途・標題欄ラベル・表ヘッダー・改定・断面のキーワードを追加/置換（merge/replace）。`config.py: KeywordConfig`。→ 5-A の解消。
- **INSERT展開・複数シート**（`extraction.entity_source`）: `expand_inserts` で INSERT を座標変換付き展開（深さ/件数上限・循環検出つき）、`process_paperspace` でペーパースペースも処理。各要素に任意 `sheet`、展開要素に `source_block` を付与。`parsers/entity_source.py`。→ 5-C の主要部を解消。
- **単位・尺度の自動スケール**（`structurize.scale.auto_scale`）: 外接範囲（＋`$INSUNITS`）からスケール係数を推定し、DBSCAN epsilon と関連付けしきい値へ乗算。`analyzers/scale_estimator.py`、出力 `metadata.scale_context`。→ 5-D の解消。
- **作図規約プロファイル**（`structurize.profile`）: 標題欄領域、断面記号パターン、部品番号流儀（バルーン対応）を切替。`config.py: DrawingProfileConfig`。→ 5-B の主要部を解消。

詳細仕様・契約は `specs/005-drawing-generalization/`（spec/plan/contracts）を参照。

## 2. 設定可能なパラメータ

`config.yaml` で変更できる主なしきい値（`config.py`）:

| 設定キー | 既定 | 用途 |
|----------|------|------|
| `dxf.supported_versions.min/max` | R12 / R2018 | 対応DXFバージョン範囲 |
| `extraction.text_dimension.duplicate_threshold` | 5.0 | テキスト寸法の重複判定距離 |
| `extraction.clustering.epsilon` | 20.0 | DBSCANの近傍半径（ブロック検出） |
| `extraction.clustering.min_samples` | 2 | DBSCANの最小サンプル数 |
| `structurize.confidence_threshold` | 0.0 | 関連付けの信頼スコア下限 |
| `structurize.tolerances.delta` | 2.0 | 寸法端点マッチング許容 |
| `structurize.tolerances.d_threshold` | 5.0 | 注記-形状距離しきい値 |
| `structurize.tolerances.delta_y_ratio` | 0.5 | テーブル同一行判定 |
| `llm.enabled/provider/model/mode/priority` | — | LLM全体制御（`provider` で openai/anthropic/azure を選択） |
| `llm.azure.{deployment,endpoint,api_version,auth_method}` | "/"/2024-10-21/azure_cli | Azure AI Foundry。`auth_method=azure_cli` で Azure CLI 認証（APIキー不要） |
| `extraction.llm.enabled` / `structurize.llm.enabled` | None（継承） | フェーズ別LLM上書き（006） |
| `structurize.rules_config` | None | 体系化ルール設定JSONのパス（006。未指定で現行構成） |
| `execution.mode` | run | サブコマンド省略時の既定（extract/structurize/run、006） |
| `extraction.keywords.{layer_purpose,title_block_labels,table_headers,revision,section,merge_mode}` | 現行と同一 | 多言語キーワード辞書（US1。merge/replace） |
| `extraction.entity_source.{expand_inserts,max_depth,max_entities,process_paperspace}` | false/5/100000/false | INSERT展開・複数シート（US2） |
| `structurize.scale.{auto_scale,base_unit,reference_size}` | false/mm/null | 単位・尺度の自動スケール（US3） |
| `structurize.profile.{title_block_region,title_block_ratio,section_symbol_pattern,part_number_style}` | bottom/0.2/`A-A`/integer_text | 作図規約プロファイル（US4） |

## 3. 既知の制限・残課題

### 3-1. LLM無効時に縮退する処理

- **ブロック種別 `table`/`notes`/`frame`/`sub_view` はLLMラベリングでのみ付与される**。
  抽出段階では全ブロックが `part_view`。そのため:
  - Rule8（標題欄＝最下端tableブロック）は、LLM無効時は「図面下端20%エリア」へフォールバック。
  - Rule9-1（notesブロック）は、LLM無効時は `Note(s)` ヘッダーテキストで代替。
  → 標題欄・改定情報の精度はLLM有効時に向上する。

### 3-2. 未使用・暫定実装

- `prompts.py: FRAME_DETECTION_PROMPT` は定義のみで**未使用**（図枠判定はルールベース）。
- `tolerance_parser.py`: 引数 `dimensions` は受け取るが未使用（公差を寸法へ紐づけていない）。
  また `_SYMMETRIC` / `_SYMMETRIC_ASCII` パターンは定義のみで `_extract_from_text` では未使用。
- `rule4_cross_section.py`: 切断線方向（4-3）は常に `direction:unknown`（方向判定は未実装）。

### 3-3. 幾何精度の制限

- SPLINEは制御点列で近似（真の曲線形状ではない）。
- ELLIPSE / HATCH は `OtherGeometry` として記録（bboxは算出するが厳密形状は保持しない）。
- INSERT（ブロック参照）は形状として展開せず無視される（テキスト/寸法系と同様）。
- 座標は2D（x,y）のみを対象とし、z は無視。

### 3-4. ヒューリスティックの限界

- テーブル検出は「閉矩形」または「格子線交差数」のヒューリスティック。
  ネスト表・結合セル・罫線のない表は正しく取れない場合がある。
- 多くのしきい値（標題欄の `_HORIZ_Y_TOL`/`_VERT_X_TOL`、テキスト幅係数、図枠面積比など）は
  **コード内ハードコード**で、`config.yaml` から変更できない（設定化の余地）。

### 3-5. 性能

- 5MB以下のDXFを目安とし、5MB超は警告を出す（性能保証外）。

## 4. 対応できる図面の範囲（推定）

本プログラムは「**2D機械部品図（JIS系の作図規約）**」を主眼に設計されている。
抽出（形状・寸法・テキスト・表・レイヤ）は規約に依存せず広く動くが、**構造化（関連付け・意味付け）は
作図規約・言語・レイヤ命名の前提に依存する**ため、図面の種類によって精度が大きく変わる。

以下は対応度の**推定**（◎=高精度、○=概ね可、△=部分的/要LLム、×=ほぼ非対応）。
「抽出」＝図形・寸法・テキスト等が取れるか、「構造化」＝関連付け・標題欄・部品表などの意味付けが取れるか。

| 図面の種類 | 抽出 | 構造化 | 推定カバー率の目安 | 主な制約 |
|------------|:----:|:------:|------------------|----------|
| 2D機械部品図（JIS、mm、罫線付き表、下部標題欄、R12〜R2018） | ◎ | ◎(LLM)/○(無LLM) | 構造化 80〜90% | 最も想定された形 |
| 2D機械部品図（英語ラベル） | ◎ | ○ | 構造化 60〜75% | 一部キーワードのみ対応 |
| 2D機械組立図（部品番号・部品表あり） | ◎ | ○ | 部品番号が整数テキストなら○ | バルーン記号(INSERT)は× |
| 板金・単品図（寸法主体） | ◎ | ○ | 寸法・形状は良好 | 曲げ表等の特殊表は△ |
| 非標準レイヤ命名／その他言語（中国語・独語等） | ◎ | △ | 構造化 30〜50% | 用途=その他に縮退、標題欄/表ヘッダ取りこぼし |
| INSERTブロック多用（標題欄・記号を部品化） | △ | △ | — | INSERTは展開されず無視（下記5-C） |
| ペーパースペース/複数シート図 | △ | △ | — | モデルスペースのみ処理（5-C） |
| isometric/3D・等角投影図 | △ | × | — | 投影関係は直交視図前提（Rule6） |
| 配管(P&ID)・電気回路・建築・土木図 | ○(図形) | × | — | 分野固有の規約・記号に非対応（5-G） |
| inch単位・特殊スケールの図面 | ◎ | △ | — | しきい値がmm前提でクラスタ/マッチング劣化（5-D） |
| R2021以降など新しいDXF | × | × | — | バージョン範囲外で読込前に終了（5-E） |

**まとめ（推定）**: 「日本語・JIS系・2D・mm・罫線付き表・下部標題欄・R12〜R2018・5MB以下」という
典型的な機械部品図であれば、LLM併用で構造化まで高精度に対応できる。そこから外れる軸（言語・分野・
作図規約・単位・エンティティ種別）が増えるほど、抽出は保てても**構造化（意味付け）の精度は段階的に低下**する。

## 5. 図面の多様性に向けた残課題（汎用化）

「ルールが一意でない（図面ごとに作図流儀が異なる）」図面に広く対応するための課題を、影響度の高い順にまとめる。

### 5-A. 言語・キーワードのハードコード（影響大）

意味付けの多くが**コード内の固定キーワード**に依存しており、日本語＋一部英語に最適化されている。

| 箇所 | 固定キーワード例 | 外れた場合の挙動 |
|------|------------------|------------------|
| レイヤ用途（`layer_extractor`） | 外形線/寸法線/中心線/注記/図枠, outline/dim/center/note/frame | `その他` に縮退 |
| 標題欄ラベル（`rule8`/`metadata_extractor`） | 作成/設計/照査/承認/材料/尺度/図番, Title/DRAWING/SCALE/REV | 標題欄項目が取れない |
| 表ヘッダー（`rule3`） | 番号/品名/型番/数量/材料/備考/NO | 先頭行をヘッダーと仮定（誤検出の可能性） |
| 改定（`rule9`） | 改定/REV/revision | 改定情報を取りこぼす |
| 断面（`rule4`） | レイヤ cross/section | 断面記号パターンのみに依存 |

- **✅ 実装済み（005、オプトイン）**: キーワード辞書を `extraction.keywords` へ外出し（多言語辞書化、merge/replace、
  レイヤ用途は完全一致＞部分一致＞最長優先で解決）。既定は現行と同一。`config.py: KeywordConfig`。
- **残る方針**: LLMによる用途・ラベル分類（カテゴリB/Cの拡大）はさらなる汎用化の選択肢。

### 5-B. 作図規約の前提（影響大）

特定の慣習を暗黙の前提にしているため、流儀の異なる図面で誤検出・取りこぼしが起きる。

- **標題欄は最下端／図面下部20%にある**前提（`rule8`）。→ **✅ 実装済み**: `structurize.profile.title_block_region`
  （`top_right` 等）/`title_block_ratio` で領域を変更可能（005）。
- **直交投影（第三角法等）を座標軸の重なりで判定**（`rule6`）。等角・透視・展開図は対象外（**未対応**）。
- **断面記号は `A-A` または単一英字 A〜Z**（`rule4`）。→ **✅ 実装済み**: `structurize.profile.section_symbol_pattern`
  で数字断面等のパターンに変更可能（005）。`DETAIL B`・詳細円は専用検出が別途必要。
- **部品番号は part_no/text レイヤの整数テキスト**（`rule10`）。→ **✅ 実装済み**: `structurize.profile.part_number_style=balloon/both`
  ＋INSERT展開で円囲みバルーン番号に対応（005）。
- **残る方針**: 投影規約の汎用化・詳細記号の専用検出・検出のLLMフォールバック化。

### 5-C. エンティティ網羅（影響大）

- **INSERT（ブロック参照）** → **✅ 実装済み（005、オプトイン）**: `extraction.entity_source.expand_inserts` で
  `virtual_entities()` により座標変換つき再帰展開（深さ/件数上限・循環検出）。由来ブロック名を `source_block` に保持。
  `parsers/entity_source.py`。
- **モデルスペースのみ処理** → **✅ 実装済み（005、オプトイン）**: `extraction.entity_source.process_paperspace` で
  全レイアウトを列挙し、各要素に帰属シート `sheet` を付与。
- **特殊シンボル非対応**: 幾何公差(GD&T)の枠、溶接記号、表面性状記号、データム等の意味解釈は無し（**未対応**）。
- **表検出が罫線前提**: 閉矩形か格子線が必要。罫線なし表・結合セル・ネスト表は取りこぼす（**未対応**。
  ただしINSERT製の表は展開後に拾える）。
- SPLINE/ELLIPSE/HATCH は近似または `OtherGeometry`（厳密形状は保持しない、**未対応**）。

### 5-D. 単位・尺度・座標スケール（影響中）

- 関連付けのしきい値（`delta=2.0`, `d_threshold=5.0`, クラスタ `epsilon=20.0` など）は
  **mm単位・一般的な図面サイズを暗黙の前提**にした絶対値。inch単位や極端に大小の図面では、
  DBSCANクラスタリングや端点マッチングが過剰/過少になり構造化が劣化する。
- `dxf.coordinate_normalization` 設定は**定義のみで未実装（no-op）**。座標正規化は効かない。
- **✅ 実装済み（005、オプトイン）**: `structurize.scale.auto_scale` で図面の外接範囲（＋`$INSUNITS`）から
  スケール係数を推定し、DBSCAN epsilon と関連付けしきい値へ乗算（`analyzers/scale_estimator.py`、出力 `metadata.scale_context`）。
  これにより mm/inch/拡大版で構造化が等価になる。
- **残る方針**: `coordinate_normalization` の実装（座標自体の正規化）は引き続き未対応。

### 5-E. DXFバージョン（影響中）

- 対応は **R12〜R2018（AC1009〜AC1032）** のみ。R2021以降など新しい版（AC1035+）は範囲外として読込前に終了する。
- 拡張方針: `dxf_reader` のバージョンマップと `supported_versions` を更新。

### 5-F. LLM無効時の構造化の縮退（影響中）

- ブロック種別（table/notes/frame/sub_view）は**LLMラベリングでのみ付与**されるため、LLM無効時は
  標題欄（Rule8）・改定（Rule9-1）がフォールバック動作になり精度が落ちる（[llm_usage.md](./llm_usage.md) 参照）。
  なおフォールバックの標題欄領域は `structurize.profile.title_block_region` で調整できる（005）。
- 規約から外れた図面ほどLLMの寄与が大きい。汎用化にはカテゴリB/Cの強化が有効。

### 5-G. 図面分野そのものの前提（影響大・スコープ外）

- 本ツールは**機械系2D図面**を前提とする。配管(P&ID)・電気回路・建築・土木などは、レイヤ運用・記号体系・
  「部品表」「標題欄」の意味自体が異なるため、現行ルールはほぼ機能しない（抽出＝図形/テキストは取れる）。
- 拡張方針: 分野別のルールセット（プラグイン的な associators 群）を切り替えられる設計にする。
  ルールの切替は外部JSON設定（`structurize.rules_config`）で、新規ルール追加は「1-1b」の拡張点（`associators/registry.py` への登録）で局所的に可能なため、分野別パックの素地はある。

## 6. テストでの品質担保

- 抽出・各ルールごとのユニットテスト（`tests/unit/`）。
- 統合CLIのE2E・LLMスイッチ・退行・汎用DXF（`tests/integration/`）。
- LLM無効時の出力同等性はゴールデン比較で機械的に担保（[output_format.md](./output_format.md) の非決定行を除外）。
- 汎用化拡張（005）のテスト: 多言語キーワード・INSERT展開/複数シート・スケール不変・作図規約プロファイル・
  縮退可視性の各テスト（`tests/unit/test_{keyword_config,keyword_resolution,entity_source,scale_estimator,drawing_profile,serialize_sheet}.py`、
  `tests/integration/test_{keyword_multilingual,insert_expansion,multi_sheet,scale_invariance,drawing_profile,degradation_visibility}.py`）。
  フィクスチャは `tests/fixtures/generalization/builders.py` が ezdxf で動的生成する。
- 注: 分野別（P&ID・電気・建築等）の網羅的テストは引き続き未整備。

---

関連: [処理フロー（ハブ）](./processing_flow.md) / [リファクタリング結果](./refactoring_result.md) / [LLM利用](./llm_usage.md)
