# ドキュメント要約: DXF図面構造化ツール

本書は `docs/` 配下の各ドキュメントの**要約**である。詳細は各セクション見出しのリンク先（相対パス）を参照すること。

## 目次

1. [全体像（処理フロー）](#1-全体像処理フロー)
2. [抽出フェーズ（DXF→抽出データ）](#2-抽出フェーズdxf抽出データ)
3. [構造化ルール（抽出データ→構造化データ）](#3-構造化ルール抽出データ構造化データ)
4. [LLM利用の全容（A/B/C分類）](#4-llm利用の全容abc分類)
5. [出力形式（構造化データ→ファイル）](#5-出力形式構造化データファイル)
6. [リファクタリング結果（CLI統合）](#6-リファクタリング結果cli統合)
7. [拡張性と残課題](#7-拡張性と残課題)
8. [汎用化拡張（005）早見表](#8-汎用化拡張005早見表)
9. [元ドキュメント一覧](#9-元ドキュメント一覧)

---

## 1. 全体像（処理フロー）

> 詳細: [processing_flow.md](./processing_flow.md)

機械図面の **DXFファイル**を入力し、要素（線・円・寸法・文字・表）を取り出し、要素間の関係を整理して、**構造化JSON**（機械可読）と**Markdownレポート**（人間可読）を出力するツール。

```
DXFファイル ──→ ① 抽出 ──→ 抽出データ ──→ ② 構造化 ──→ 構造化データ ──→ ③ 出力
 (.dxf)              (DXFDrawing)              (StructuredDrawing)      (.json / .md)
```

担当モジュールの連鎖:

| 順 | 担当 | 役割 |
|----|------|------|
| 1 | `cli.py` | コマンド引数・設定の読み込み（受付係） |
| 2 | `orchestrator.py` | 抽出→構造化を連結（進行係）。`OrchestrationResult` を返す |
| 3 | `pipeline.py: run_pipeline()` | ①抽出（DXF→`DXFDrawing`） |
| 4 | `structurize_pipeline.py: StructurizePipeline.run()` | ②構造化（`DXFDrawing`→`StructuredDrawing`） |
| 5 | `serializers/` | ③JSON・Markdownへ変換して保存 |

- 処理は **(a) 抽出フェーズ** と **(b) 体系化フェーズ** に分かれ、`dxf-extract` の3サブコマンド（`extract` / `structurize` / `run`）で個別にも連続にも実行できる（仕様 `specs/006-split-extract-structurize/`）。(a)の出力（抽出JSON）が(b)の入力となり、`extract`→`structurize` は `run` の連続実行と同一結果になる。サブコマンド省略時は `config.yaml` の `execution.mode`（既定 `run`）に従う。
- LLMの有無は**フェーズごとに個別指定**できる（`extraction.llm` / `structurize.llm` の `enabled`、未指定はトップレベル `llm.enabled` を継承）。`--llm` / `--no-llm` は起動サブコマンドの対象フェーズを上書きする。既定は両フェーズ無効。`orchestrator.py` が `effective_extraction_llm()` / `effective_structurize_llm()` で実効値を解決する。
- `--no-llm`: 外部AIを一切呼ばない（カテゴリAのみ、オフライン可）。`--llm`: 精度改善のためAIを併用（カテゴリA＋B）。
- LLM無効時の出力が従来と同等であることは退行テストで担保（[後述](#6-リファクタリング結果cli統合)）。

---

## 2. 抽出フェーズ（DXF→抽出データ）

> 詳細: [extraction_details.md](./extraction_details.md)

担当 `pipeline.py: run_pipeline()`。DXFを開き要素を種類ごとに取り出して1つの `DXFDrawing` にまとめる。全工程**カテゴリA**で、各抽出は `_safe_extract()` で包まれ、**1つ失敗しても警告を残して継続**する（FR-012 / 憲章I）。未対応の要素も黙って捨てずに警告として残す。

実行順（0〜12）:

| 順 | 処理 | 担当 | カテゴリ | 出力 |
|----|------|------|----------|------|
| 0 | ファイルサイズ確認（5MB超で警告） | `_check_file_size` | A | 警告のみ |
| 1 | DXF読込・バージョン検証 | `dxf_reader.py` | A | ezdxf Drawing |
| 2 | 形状抽出 | `shape_extractor.py` | A | `shapes` |
| 3 | 寸法抽出 | `dimension_extractor.py` | A | `dimensions` |
| 4 | テキスト抽出（注記/テキスト寸法に分離） | `text_extractor.py` | A | `notes`, `text_dimensions` |
| 5 | 表抽出 | `table_extractor.py` | A | `tables` |
| 6 | レイヤ抽出 | `layer_extractor.py` | A | `layers` |
| 7 | 公差解析 | `tolerance_parser.py` | A | `tolerances` |
| 8 | テキスト寸法の重複解決 | `duplicate_resolver.py` | A | `text_dimensions`（更新） |
| 9 | 論理ブロック検出（DBSCAN） | `block_detector.py` | A | `blocks` |
| 10 | 図枠検出 | `frame_detector.py` | A | 図枠ブロック添字 |
| 11 | メタ情報抽出 | `metadata_extractor.py` | A | 図番・尺度等 |
| 12 | **LLMラベリング（任意）** | `llm/labeler.py` | **B** | `blocks`/`layers` の種別・用途を上書き |

主要な抽出処理:

- **形状抽出**: LINE→`LineGeometry`、CIRCLE→`CircleGeometry`、ARC→`ArcGeometry`、LWPOLYLINE/POLYLINE/LEADER/SPLINE→`PolylineGeometry`、HATCH/ELLIPSE→`OtherGeometry`。TEXT/MTEXT/DIMENSION/INSERTは形状として扱わず別処理。**未対応種別も `OtherGeometry`（生属性付き）で記録**。ID採番 `shape_001`…、各形状に外接矩形 `bounding_box` を付与。
- **寸法抽出**: `DIMENSION` の `dimtype` 下位4ビットで種別判定（0→linear/1→angular/2→diameter/3→radial/6→ordinate）。方向は `dxf.angle` 等から x/y/parallel を判定（許容0.5°）。引出点 `extension_point_1/2` を保持→Rule1の端点マッチングで使用。
- **テキスト抽出**: 数値のみ（正規表現）→テキスト寸法 `tdim_001`…、それ以外→注記 `note_001`…。MTEXTは書式コード除去・`\P`を改行化。
- **表抽出**: 閉じたLWPOLYLINE矩形、またはLINE群の格子（交差4以上）を検出。矩形内テキスト2個以上で採用。y座標を許容2.0でクラスタリングして行、x昇順で列。
- **公差解析**: 注記から正規表現で抽出。grade（`H7/g6`）、bilateral（`+0.1/-0.2`）、symmetric（`±0.05`）。
- **論理ブロック検出**: 形状・寸法・注記の重心座標をDBSCAN（epsilon=20.0, min_samples=2）でクラスタリング。**この段階では全ブロック `type=part_view` 固定**（`table`/`notes`/`frame`/`sub_view` への分類はLLMラベリングでのみ実施）。bbox面積0の形状は原点誤混入を防ぐため除外。
- **図枠検出**: レイヤ用途 `図枠` かつ注記2以上のブロックを候補に。特定できなければ面積比0.3以上にフォールバック。
- **メタ情報抽出**: 図枠内注記から図番・タイトル・改訂・尺度・作成/確認/承認者を抽出。同一テキスト内（パス1）と、ラベルのみ＋右隣の近接テキスト（パス2、距離30/dy10以内）の2方式。

**汎用化拡張（005、オプトイン）**: 各抽出は共通の `parsers/entity_source.py` を反復元とする。`extraction.entity_source` でINSERT展開（座標変換つき）・ペーパースペース/複数シート処理を有効化でき、各要素に帰属シート `sheet`・由来ブロック `source_block` が付く。ブロック検出前段で `analyzers/scale_estimator.py` がスケール係数を推定（`structurize.scale.auto_scale` 有効時）。既定無効で従来挙動と一致。

---

## 3. 構造化ルール（抽出データ→構造化データ）

> 詳細: [structurization_rules.md](./structurization_rules.md)

担当 `structurize_pipeline.py: StructurizePipeline.run()`。要素間の関係を**10ルール**（`associators/rule1`〜`rule10`）で順番に判定し、`AssociationResult` の列として `StructuredDrawing.associations` に蓄積する。**ルールの有効/無効・適用順・パラメータ**は外部JSON設定（`structurize.rules_config`）で変更でき、`associators/registry.py`（既定順＝現行と同一）と `associators/rule_loader.py` が解決する。未指定なら現行構成・ゴールデン不変（FR-014〜017）。全ルールは `AssociatorBase` を継承（Template Methodパターン）し、`run()` が信頼スコアでフィルタ（`confidence >= structurize.confidence_threshold`、既定0.0で全件採用）。1ルールが例外を投げても次へ継続。

`AssociationResult` のフィールド: `rule`（サブルール番号）/ `source_id`（関連付け元）/ `target_ids`（関連付け先IDまたは意味ラベル `section:A`・`metadata.scale` 等）/ `confidence`（0.0〜1.0）/ `extracted_value`（抽出値、任意）/ `llm_augmented`・`llm_error`。

実行順（依存あり: 先に表・標題欄・断面を確定 → 寸法/視図/部品番号 → 注記）:

| 順 | ルール | 内容 | LLM補完 |
|----|--------|------|---------|
| 1 | Rule3 | テーブル構造化（境界/ヘッダー/列名） | 3-1 |
| 2 | Rule8 | 標題欄構造化（領域特定/ラベル-値ペア/NTS） | 8-2 |
| 3 | Rule9 | 改定情報・注記エリア抽出 | 9-2 |
| 4 | Rule4 | 断面表示関連付け（記号抽出/ブロック紐づけ/方向） | — |
| 5 | Rule7 | ハッチング関連付け（境界/LEADER/断面） | 7-2 |
| 6 | Rule1 | 寸法↔形状マッチング（端点/円/ブロック帰属） | — |
| 7 | Rule6 | 視図間投影関係（座標軸/共通寸法） | — |
| 8 | Rule10 | 部品番号紐づけ（識別/ビュー/表行） | — |
| 9 | Rule2 | テキスト寸法分類（レイヤ/位置） | — |
| 10 | Rule5 | 注記↔形状対応（レイヤ/LEADER/近接） | 5-3 |

各ルールの要点:

- **Rule1（寸法↔形状）**: linear寸法の引出点が形状端点から `delta`（既定2.0）以内で対応（1.0）。径/直径寸法は円の半径内 `CircleGeometry` に対応。引出点がブロックbbox内ならブロック帰属。
- **Rule3（テーブル）**: テーブルを含むブロックを対応付け。`番号/品名/型番/数量/材料` 等のキーワード行をヘッダーとし（無ければ先頭行）、列順に `col:i:列名` を生成。**LLM有効時はヘッダー特定の精度向上**。
- **Rule4（断面）**: 注記から断面記号（`A-A`/単一英字）を抽出→ `section:A`。名前に記号を含むブロックを対応（無ければ最近傍0.7）。切断線方向は常に `unknown`（未実装）。
- **Rule5（注記↔形状）**: レイヤ大分類→ `category:annotation/cross/table`。注記位置がLEADER bboxから `d_threshold`（既定5.0）以内で対応。近接非LEADER形状の最近傍を採用（**LLM有効時は候補から最適形状をLLM判定**）。
- **Rule6（視図間投影）**: `part_view` が2つ以上のとき、x範囲が重なりy方向に離れる（正面↔上面）/ y範囲が重なりx方向に離れる（正面↔側面）対を対応。同じ寸法IDを共有する対も対応。
- **Rule7（ハッチング）**: ハッチbbox内包の閉形状を境界に（無ければ `no_boundary` 0.5）。同一ブロック内LEADERを対応（**LLM有効時はLLM特定**）。レイヤ `cross` を含めば `cross_section`。
- **Rule8（標題欄）**: `table` 型ブロックの**最下端**を標題欄とする。標題欄内注記からラベル（作成/設計/照査/承認/材料/尺度/図番…）を検出し、対応する値注記（水平＝右隣、垂直＝下方）を `extracted_value` に紐づけ（**LLM有効時はLLMが値テキストを返す**）。`NTS` テキストは `metadata.scale="NTS"`。**LLM無効時は `table` ブロックが無いため図面下端20%エリアへフォールバック**。
- **Rule9（改定情報）**: `notes` 型ブロックまたは `Note(s)` ヘッダーを `metadata.notes_area` に。`REV/改定/revision` を含む注記から改定内容を抽出（**LLM有効時はLLMが整形抽出**）。
- **Rule10（部品番号）**: 部品番号レイヤかつ整数値かつ非重複のテキスト寸法を `part_number:N` に。番号位置が `part_view` bbox内なら対応（無ければ最近傍0.7）。部品表の「番号」列の同値行を `table:row:idx` に対応。
- **Rule2（テキスト寸法分類）**: レイヤ名で `寸法線`/`テーブル番号` に分類。テーブルbbox内ならそのテーブルに対応。

ルール適用後、`_apply_metadata()` が `target_ids` が `metadata.*` を指し `extracted_value` を持つ関連付けを `metadata`（title/drawing_number/scale/created_by/designed_by/checked_by/approved_by/material/revision）に反映する。既存のDXF属性値は基本上書きしない。`revision` は複数あれば改行追記、`scale` は実数尺度を `NTS` より優先。

信頼スコア（既定）: 1.0=確定的な関連付け、0.8=Rule4-3（方向unknown）、0.7=最近傍フォールバック、0.5=Rule7-1（境界なし）・LLM失敗フォールバック。

---

## 4. LLM利用の全容（A/B/C分類）

> 詳細: [llm_usage.md](./llm_usage.md)

LLM使用の有無は**フェーズごとに解決**する（抽出=`config.effective_extraction_llm()`、体系化=`config.effective_structurize_llm()`。各 `extraction.llm` / `structurize.llm` の `enabled`、未指定はトップレベル `llm.enabled` を継承）。**接続情報・生成点は単一**で、`llm/provider.py: create_llm()` のみ（LangChain `init_chat_model`、利用環境は `llm.provider` で選択: openai/anthropic/azure、既定 `gpt-5-mini`）。認証は openai/anthropic がAPIキー（`.env`）、**Azure AI Foundry は既定で Azure CLI 認証**（`az login` のAzure ADトークン、APIキー不要。`azure.auth_method`）。生成点が単一のため、LLM呼び出しの有無はこの関数の呼び出し回数で判定でき、退行テスト・スイッチテストがこれを利用する。

LLMを使う箇所（**限定的・補助的**。大半はカテゴリAで完結）:

- **抽出フェーズのラベリング**（`llm/labeler.py`、抽出フェーズの実効LLM有効時のみ）:
  - 論理ブロック種別（`BLOCK_TYPE_PROMPT` → `part_view/sub_view/table/frame/notes`、失敗時は既定 `part_view` 維持）。
  - レイヤ用途（`LAYER_PURPOSE_PROMPT` → `外形線/寸法線/中心線/補助線/注記/図枠/その他`、失敗時は元の用途維持）。
  - ブロック・レイヤごとに1回 `llm.invoke()`。失敗は個別に握りつぶし、`label_with_llm` 全体が例外でも警告ログを出しルールベース結果で継続。
  - **`table`/`notes` 種別はLLMでしか付与されない**ため、Rule8・Rule9-1の精度はLLM有効時に向上する。
- **構造化フェーズのルール補完**（`associators/llm_helper.py: try_llm_augment`、`llm_config is not None` 時のみ）の**5サブルール**:

  | サブルール | LLMにさせること | フォールバック（A） |
  |------------|------------------|---------------------|
  | 3-1 | テーブルのヘッダー行特定 | キーワード一致の `row:idx` |
  | 5-3 | 注記が指す形状の判定 | 最近傍の形状 |
  | 7-2 | ハッチに対応するLEADER特定 | 同一ブロック内のLEADER候補 |
  | 8-2 | 標題欄ラベルに対応する値抽出 | 近接探索で得た値 |
  | 9-2 | 改定情報テキストの整形抽出 | 正規表現による行抽出 |

  `try_llm_augment` は `LangChainException`/タイムアウト/接続エラーを捕捉し、カテゴリA相当のフォールバック（confidence 0.5、`llm_error=True`）を返す。APIキー未設定・ネットワーク不通でも処理は止まらず成果物は必ず生成される。

カテゴリ分類:

| 分類 | 定義 | 該当 |
|------|------|------|
| **A: プログラムのみ** | LLM不要 | 全抽出、Rule1/2/4/6/10、各フォールバック、シリアライズ |
| **B: LLMで精度改善** | プログラムでも可・LLMで向上 | ラベリング（ブロック/レイヤ）、Rule 3-1/5-3/7-2/8-2/9-2 |
| **C: LLM必須** | プログラム単独で困難 | 現状該当なし（将来枠、分類・文書化のみ） |

未使用・拡張余地: `prompts.py: FRAME_DETECTION_PROMPT`（図枠判定）は定義済みだが未使用（図枠検出は `frame_detector.py` のルールベース）。カテゴリC枠は未実装。

---

## 5. 出力形式（構造化データ→ファイル）

> 詳細: [output_format.md](./output_format.md)

担当 `cli.py`（書き出し）＋ `serializers/`。`<名前>` は入力DXFの拡張子なしファイル名、出力先は `--output-dir`（未指定時は入力と同じ場所）。

| ファイル | 担当 | 条件 |
|----------|------|------|
| `<名前>_structured.json` | `StructuredDrawing.model_dump_json` | 常に生成 |
| `<名前>_structured.md` | `serializers/md_serializer.py` | 常に生成 |
| `<名前>.json`（抽出JSON） | `serializers/json_serializer.py` | `--save-intermediate` 時のみ |

- **構造化JSON**: 抽出データ（`DXFDrawing`）の全フィールド（metadata/blocks/shapes/dimensions/text_dimensions/tolerances/tables/notes/layers）に **`associations`**（構造化JSONのみ。抽出JSONには無い）を加えたもの。`blocks[].type` は part_view/sub_view/table/frame/notes、`dimensions[].dim_type` は linear/diameter/radial/angular/ordinate、`tolerances[].tol_type` は grade/bilateral/symmetric。
- **汎用化拡張の任意フィールド（005、オプトイン）**: 対応設定有効時のみ付与され、既定（無効）では出力に現れず従来スキーマと一致（`models/shape.py: OmitNoneMixin` が `None` 時に省略）。
  - `sheet`（shapes/dimensions/notes/tables）← `process_paperspace: true`、帰属シート名。
  - `source_block`（shapes[].geometry の OtherGeometry のみ）← `expand_inserts: true`、由来ブロック名。
  - `scale_context`（metadata）← `auto_scale: true`、`{unit, factor, source}`（採用単位・係数・推定根拠 insunits/bbox/default）。
- **Markdownレポート**: ヘッダ（`# 図面体系化レポート: <入力名>`、生成日時/処理モード）＋11セクション = ①標題欄 ②部品表 ③部品詳細 ④断面関係 ⑤視図グループ ⑥注記・改定情報 ⑦形状一覧 ⑧寸法一覧 ⑨許容差一覧 ⑩論理ブロック一覧 ⑪処理サマリー。「処理モード」は `OrchestrationResult.mode`（LLM無効=カテゴリA、有効=カテゴリA+B）。「生成日時」は非決定的のため退行比較ではタイトル/生成日時の2行を除外して本文比較する。
- **終了コード（FR-016）**: 0=正常、1=一般エラー（書込/処理中）、2=入力フォーマット不正（DXF読込/バージョン検証失敗、引数不正）、3=設定ファイル不正。実装は `cli_support.py`（定数）＋ `cli.py`（例外→コード対応）。エラーメッセージはすべて日本語。

---

## 6. リファクタリング結果（CLI統合 → 2フェーズ分割）

> 詳細: [refactoring_result.md](./refactoring_result.md)

**004（CLI統合）**: 2本のCLI（`dxf-extract` / `dxf-structurize`）を **`dxf-extract` 1本**へ統合。DXF入力から構造化JSON＋Markdown生成までを単一コマンドで一気通貫実行する。

**006（2フェーズ分割・ルール外部化）**: その `dxf-extract` を **(a) 抽出 / (b) 体系化** の2フェーズに分け、`extract` / `structurize` / `run` の3サブコマンドで個別・連続実行を選べるようにした（仕様 `specs/006-split-extract-structurize/`）。実行モード既定は `execution.mode`、LLM有無はフェーズ個別（`extraction.llm` / `structurize.llm`）、体系化ルールは外部JSON（`structurize.rules_config`）で設定可能。抽出JSONの読み戻しは `json_serializer.load_drawing`。`extract`→`structurize` ＝ `run` の同値・`--no-llm` ゴールデン不変を維持。

- 旧 `dxf-structurize` エントリポイントと `structurize_cli.py` を削除。`pyproject.toml` の `[project.scripts]` は `dxf-extract` 1本に統合。中間の抽出JSONは `--save-intermediate` で取得。
- **重複処理の統合**: 設定読込（`load_config`）、ロギング/進捗表示（`cli_support.setup_logging` に統一、`--log-level quiet` で抑制）、出力パス解決（`resolve_output_dir`/`output_paths`）、LLM有効判定（フェーズ別 `effective_extraction_llm`/`effective_structurize_llm`）、エラー終了処理（`error_exit` ＋終了コード規約）、パイプライン連結（`orchestrator.run_extract`/`run_structurize`/`run_all`）。各サブコマンドはこれら共通処理へ委譲する。
- **新規モジュール**: `cli_support.py`（ロギング・出力パス・エラー終了・終了コード定数）、`orchestrator.py`（`run_extract`/`run_structurize`/`run_all` の分割関数、フェーズ別にLLM可否を適用。旧 `run` はエイリアスとして温存）。
- **処理の3分類（A/B/C）**: LLM使用要否で各処理を分類。LLM無効時はカテゴリAのみ実行。カテゴリCは枠組み定義に留め、該当処理追加時にLLM有効時の成果物へ反映する。
- **退行防止**: リファクタリング前に `--no-llm` で生成した成果物を `tests/fixtures/golden/` にゴールデン保存。統合CLIの `--no-llm` 出力（構造化JSON＝完全一致、Markdown＝タイトル/生成日時を除く本文一致）がゴールデンと一致することを `tests/integration/test_no_llm_regression.py` で検証。

---

## 7. 拡張性と残課題

> 詳細: [extensibility_and_issues.md](./extensibility_and_issues.md)

**拡張のしかた**:
- **構造化ルール設定（コード改修なし）**: 既存ルールの有効/無効・適用順・パラメータは外部JSON（`structurize.rules_config`）で変更可。未指定なら現行構成。**新規ルール追加**は `associators/` に `AssociatorBase` 継承クラスを作り、`associators/registry.py` の `RULE_REGISTRY`・`DEFAULT_ORDER` に1行ずつ追記するだけ。既存ルール・`run()` 本体の変更不要。信頼スコアフィルタ・例外隔離は基底クラスが共通提供。
- **新エンティティ種別**: `shape_extractor.py` の `_SUPPORTED_TYPES`/`_extract_entity()` に分岐追加、必要なら `models/shape.py` にジオメトリ型追加。
- **新parser/analyzer**: `run_pipeline()` に `_safe_extract("名称", lambda: 新処理())` で追加（失敗が全体を止めない）。
- **メタ情報/公差**: 正規表現リストや `_LABEL_FIELD_MAP`/`_METADATA_FIELD_MAP`/`Metadata` を更新。
- **ルールへのLLM補完**: `llm_config is not None` 時に `try_llm_augment()` を呼び、カテゴリA結果を `fallback_*` に渡して安全縮退。

**設定可能な主なパラメータ**（`config.yaml` / `config.py`）: `dxf.supported_versions.min/max`（R12/R2018）、`extraction.text_dimension.duplicate_threshold`（5.0）、`extraction.clustering.epsilon/min_samples`（20.0/2）、`structurize.confidence_threshold`（0.0）、`structurize.tolerances.delta/d_threshold/delta_y_ratio`（2.0/5.0/0.5）、`llm.*`。汎用化拡張のキーは[次節](#8-汎用化拡張005早見表)。

**主な既知の制限・残課題**:
- ブロック種別（table/notes/frame/sub_view）はLLMでのみ付与 → LLM無効時はRule8（標題欄＝最下端table）が下端20%エリア、Rule9-1（notesブロック）が `Note(s)` ヘッダーへフォールバックし精度低下。
- 暫定実装: `FRAME_DETECTION_PROMPT` 未使用、`tolerance_parser.py` の引数 `dimensions` と一部パターンは未使用、Rule4-3 切断線方向は常に `unknown`。
- 幾何精度: SPLINEは制御点近似、ELLIPSE/HATCHは `OtherGeometry`（bboxのみ）、INSERTは既定で無視、座標は2D（z無視）。
- ヒューリスティック限界: 表検出は閉矩形/格子線交差に依存（ネスト表・結合セル・罫線なし表は取りこぼし）。多くのしきい値（標題欄の `_HORIZ_Y_TOL` 等）はハードコードで `config.yaml` 不可。
- `dxf.coordinate_normalization` は定義のみで未実装（no-op）。対応版はR12〜R2018のみ、5MB超は性能保証外。

**対応図面の範囲（推定）**: 抽出は作図規約に依存せず広く動くが、**構造化（意味付け）は作図規約・言語・レイヤ命名の前提に依存**するため図面種類で精度が大きく変わる。「日本語・JIS系・2D・mm・罫線付き表・下部標題欄・R12〜R2018・5MB以下」の典型的な機械部品図ならLLM併用で構造化80〜90%。英語ラベルは60〜75%、非標準命名/他言語は30〜50%（用途=その他に縮退）。isometric/3D・配管/電気/建築・R2021以降は構造化ほぼ非対応。そこから外れる軸（言語・分野・作図規約・単位・エンティティ種別）が増えるほど、抽出は保てても構造化の精度は段階的に低下する。

---

## 8. 汎用化拡張（005）早見表

> 詳細: [extensibility_and_issues.md](./extensibility_and_issues.md)（§1-7, §5）。仕様は `specs/005-drawing-generalization/`。

多様な図面への対応として、**`config.yaml` の設定のみ**で有効化できる4機能。**既定はすべて無効＝従来挙動・ゴールデン不変**。

| 機能 | 設定キー | 既定 | 内容 | 解消した課題 |
|------|----------|------|------|--------------|
| 多言語キーワード辞書 | `extraction.keywords.{layer_purpose, title_block_labels, table_headers, revision, section, merge_mode}` | 現行と同一 | レイヤ用途・標題欄ラベル・表ヘッダー・改定・断面のキーワードを追加/置換（merge/replace）。レイヤ用途は完全一致＞部分一致＞最長優先。`config.py: KeywordConfig` | 5-A（言語ハードコード） |
| INSERT展開・複数シート | `extraction.entity_source.{expand_inserts, max_depth, max_entities, process_paperspace}` | false/5/100000/false | `virtual_entities()` で座標変換つき再帰展開（深さ/件数上限・循環検出）、ペーパースペース全レイアウト処理。`source_block`/`sheet` 付与。`parsers/entity_source.py` | 5-C（エンティティ網羅） |
| 単位・尺度の自動スケール | `structurize.scale.{auto_scale, base_unit, reference_size}` | false/mm/null | 外接範囲（＋`$INSUNITS`）からスケール係数を推定し、DBSCAN epsilon と関連付けしきい値へ乗算。出力 `metadata.scale_context`。`analyzers/scale_estimator.py` | 5-D（単位・尺度） |
| 作図規約プロファイル | `structurize.profile.{title_block_region, title_block_ratio, section_symbol_pattern, part_number_style}` | bottom/0.2/`A-A`/integer_text | 標題欄領域（top_right等）、断面記号パターン（数字断面等）、部品番号流儀（balloon/both でバルーン対応）を切替。`config.py: DrawingProfileConfig` | 5-B（作図規約） |

テスト: 多言語キーワード・INSERT展開/複数シート・スケール不変・作図規約プロファイル・縮退可視性の各テスト（`tests/unit/`・`tests/integration/`）。フィクスチャは `tests/fixtures/generalization/builders.py` が ezdxf で動的生成。

---

## 9. 元ドキュメント一覧

| ドキュメント | 内容 |
|--------------|------|
| [processing_flow.md](./processing_flow.md) | 全体像（DXF→抽出→構造化→出力）の俯瞰・入口ハブ |
| [extraction_details.md](./extraction_details.md) | 各parser/analyzerの抽出内容・しきい値・実行順 |
| [structurization_rules.md](./structurization_rules.md) | 全10ルール（全サブルール）の判定内容・出力・カテゴリ |
| [llm_usage.md](./llm_usage.md) | LLMの利用箇所・範囲・制御・フォールバック・A/B/C分類 |
| [output_format.md](./output_format.md) | 構造化JSONスキーマ・Markdown11セクション・終了コード |
| [refactoring_result.md](./refactoring_result.md) | CLI統合・重複削減・処理3分類の記録 |
| [extensibility_and_issues.md](./extensibility_and_issues.md) | 拡張手順・設定可能パラメータ・既知の制限・残課題 |
