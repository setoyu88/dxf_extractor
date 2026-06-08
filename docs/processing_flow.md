# 処理フロー解説: DXFから構造化情報まで（ハブ）

このドキュメントは、`dxf-extract` コマンドが **DXFファイルをどのように読み取り、
情報を取り出し、構造化していくか** を、プログラム初心者にもわかるように解説する**入口（ハブ）**である。
詳細は下記の各ドキュメントに分割しているので、必要に応じて辿ってほしい。

## 詳細ドキュメント索引

| ドキュメント | 内容 |
|--------------|------|
| 本書 | 全体像（DXF→抽出→構造化→出力）の俯瞰 |
| [抽出フェーズ詳細](./extraction_details.md) | 各parser/analyzerが何をどう抽出するか、しきい値、実行順 |
| [構造化ルール詳細](./structurization_rules.md) | **全10ルール（全サブルール）** の判定内容・手順・出力・カテゴリ |
| [LLM利用の全容](./llm_usage.md) | LLMの利用箇所・範囲・対象・制御・フォールバック・カテゴリA/B/C |
| [出力形式](./output_format.md) | 構造化JSONスキーマ・Markdown11セクション・終了コード |
| [拡張性と残課題](./extensibility_and_issues.md) | 拡張手順・設定可能パラメータ・既知の制限 |
| [リファクタリング結果](./refactoring_result.md) | CLI統合・重複削減・処理3分類の記録 |

## 0. そもそも何をするツール？

機械図面などの **DXFファイル**（CADの図面データ）を入力すると、

1. 図面に含まれる「線・円・寸法・文字・表」などの要素を取り出し、
2. それらの関係（どの寸法がどの形状のものか、標題欄の図番は何か等）を整理して、
3. **構造化JSON**（機械が扱いやすい形）と **Markdownレポート**（人が読みやすい形）

を出力する。

```
DXFファイル ──→ ① 抽出 ──→ 抽出データ ──→ ② 構造化 ──→ 構造化データ ──→ ③ 出力
 (.dxf)              (DXFDrawing)              (StructuredDrawing)      (.json / .md)
```

## 1. 全体の流れ（コマンド実行から出力まで）

`dxf-extract` は3つのサブコマンドを持つ。**(a) 抽出フェーズ**と**(b) 体系化フェーズ**を個別にも連続にも実行できる（仕様 `specs/006-split-extract-structurize/`）。

| サブコマンド | 入力 | 出力 | フェーズ |
|--------------|------|------|----------|
| `extract` | `.dxf` | 抽出JSON `<名前>.json` | (a)のみ |
| `structurize` | 抽出JSON | 構造化JSON＋Markdown | (b)のみ |
| `run` | `.dxf` | 構造化JSON＋Markdown（＋任意で抽出JSON） | (a)+(b)連続 |

サブコマンドを省略すると `config.yaml` の `execution.mode`（既定 `run`）に従う。`dxf-extract run sample/sample_libre_1.dxf` を実行すると、内部では次の順に処理が進む。

| 順 | 担当モジュール | 役割 |
|----|----------------|------|
| 1 | `cli.py` | サブコマンド・引数を読み取り、設定を読み込む（共通処理は委譲） |
| 2 | `orchestrator.py` | `run_extract`／`run_structurize`／`run_all` で抽出・構造化を連結 |
| 3 | `pipeline.py` | ①抽出（DXF→抽出データ） |
| 4 | `structurize_pipeline.py` | ②構造化（抽出データ→構造化データ。ルールは外部設定可） |
| 5 | `serializers/` | ③JSON・Markdownへ変換／抽出JSONの読み戻し（`load_drawing`） |

`cli.py` は「受付係」、`orchestrator.py` は「進行係」、その先が実際の処理だと考えるとよい。(a)の出力（抽出JSON）が(b)の入力となり、`extract`→`structurize` の2段実行は `run` の連続実行と同一の成果物になる。

## 2. ステップ①: 抽出（DXF → 抽出データ）

担当: `src/dxf_extractor/pipeline.py` の `run_pipeline()`

DXFファイルを開き、要素を**種類ごとに**取り出していく。各取り出しは
`parsers/`（読み取り）と `analyzers/`（解析）のモジュールが分担する。

| 取り出すもの | 担当 | 説明 |
|--------------|------|------|
| DXFを開く | `parsers/dxf_reader.py` | ファイルを読み、対応バージョンか確認する |
| 形状（線・円・弧など） | `parsers/shape_extractor.py` | 図形の座標や大きさを取得 |
| 寸法 | `parsers/dimension_extractor.py` | 寸法線の値・位置を取得 |
| 文字・注記 | `parsers/text_extractor.py` | 文字列を注記とテキスト寸法に仕分け |
| 表 | `parsers/table_extractor.py` | 部品表などの表を取得 |
| レイヤ | `parsers/layer_extractor.py` | 図面の「層」情報を取得 |
| 公差 | `analyzers/tolerance_parser.py` | 「±0.1」などの許容差を解釈 |
| 重複の解消 | `analyzers/duplicate_resolver.py` | 同じ寸法の重複を除去 |
| 論理ブロック検出 | `analyzers/block_detector.py` | 近い要素をまとめて「部品図」などの塊にする |
| 図枠検出 | `analyzers/frame_detector.py` | 図面の枠（外周）を見つける |
| メタ情報抽出 | `analyzers/metadata_extractor.py` | 図番・尺度・材質などを拾う |

### 大事な工夫: 一部が失敗しても止まらない

`run_pipeline()` は各取り出しを `_safe_extract()` で包んでいる。たとえば「表の取り出し」で
エラーが出ても、**警告を記録して他の取り出しは続行**する。これにより、想定外の図面でも
できる範囲の情報を出力できる（未対応の要素は黙って捨てず、警告として残す）。

### LLMはここで使うこともある（任意）

設定で **LLMが有効**なときだけ、`llm/labeler.py` がブロックの種別やレイヤの用途を
AIで補完する（精度改善 = カテゴリB）。**LLMが無効**なら、この処理は丸ごとスキップされ、
プログラムだけの判定（カテゴリA）になる。

この結果が **抽出データ（`DXFDrawing`）** という1つのまとまったデータになる。

### 汎用化のための任意処理（005、すべてオプトイン）

各取り出しは共通の供給 `parsers/entity_source.py` を反復元とする。設定で有効化すると、
**INSERT（ブロック参照）の展開**・**ペーパースペース/複数シート処理**（`extraction.entity_source`）、
**単位・尺度に応じたしきい値の自動スケール**（`structurize.scale`、`analyzers/scale_estimator.py`）、
**多言語キーワード辞書**・**作図規約プロファイル**が働く。いずれも既定は無効で、従来挙動と完全に一致する。
詳細は [拡張性と残課題](./extensibility_and_issues.md) を参照。

## 3. ステップ②: 構造化（抽出データ → 構造化データ）

担当: `src/dxf_extractor/structurize_pipeline.py` の `StructurizePipeline.run()`

抽出しただけでは「バラバラの要素の集まり」にすぎない。ここでは要素どうしの**関係**を
**全10ルール**（`associators/rule1` 〜 `rule10`）で**決まった順番**に判定し、関連付けを付けていく。
順序には依存関係がある（先に表・標題欄・断面を確定してから、寸法・視図・部品番号、最後に注記）。

| 実行順 | ルール | 何をするか | LLM補完 |
|--------|--------|------------|---------|
| 1 | ルール3 | 表（部品表など）の構造・ヘッダー・列名を識別する | 3-1 |
| 2 | ルール8 | 標題欄（図番・尺度・作成者などの欄）を構造化する | 8-2 |
| 3 | ルール9 | 改定情報・注記エリアを抽出する | 9-2 |
| 4 | ルール4 | 断面記号（A-A等）と断面図を対応付ける | — |
| 5 | ルール7 | ハッチング（断面の網掛け）と境界・引出線を対応付ける | 7-2 |
| 6 | ルール1 | 寸法線と形状（線・円）を結びつける | — |
| 7 | ルール6 | 複数の視図（正面図・側面図など）をグループ化する | — |
| 8 | ルール10 | 部品番号と部品ビュー・部品表行を紐づける | — |
| 9 | ルール2 | テキスト寸法を寸法線/テーブル番号に分類する | — |
| 10 | ルール5 | 注記（引出線・近接テキスト）と形状を対応付ける | 5-3 |

各ルールは「LLM設定が渡されていれば」`associators/llm_helper.py` を通じてAIで
曖昧な判定を補える（上表「LLM補完」列のサブルールのみ＝カテゴリB）。LLM無効時はルールベースのみ（カテゴリA）で動く。
**各ルールの全サブルール・判定手順・出力・信頼スコアは [構造化ルール詳細](./structurization_rules.md) を参照。**

判定結果は **構造化データ（`StructuredDrawing`）** にまとめられる。これは
「抽出データ＋関連付け（associations）」という形をしている。最後に、標題欄や改定情報で
抽出した値（図番・尺度・改定など）は `metadata` に反映される。

## 4. ステップ③: 出力（構造化データ → ファイル）

担当: `src/dxf_extractor/serializers/`

| 出力 | 担当 | 内容 |
|------|------|------|
| 構造化JSON `<名前>_structured.json` | `model_dump_json()` | 機械が扱いやすい構造化データ |
| Markdownレポート `<名前>_structured.md` | `md_serializer.py` | 人が読みやすい体系化レポート |
| （任意）抽出JSON `<名前>.json` | `json_serializer.py` | 中間成果物（`--save-intermediate` 時のみ） |

出力先は `--output-dir` で指定でき、未指定なら入力DXFと同じ場所に保存される。

## 5. LLMのON/OFFはどこで効く？

LLM使用の有無は**フェーズごとに個別指定**できる。トップレベル `llm`（接続情報＋全体既定）に加え、
`extraction.llm` / `structurize.llm` の各 `enabled` で抽出側・構造化側を独立に制御する
（未指定ならトップレベル `llm.enabled` を継承）。コマンドの `--llm` / `--no-llm` は、
起動したサブコマンドの対象フェーズ（`extract`→抽出、`structurize`→体系化、`run`→両方）を上書きする。

- `--no-llm`: 外部AIを一切呼ばない（カテゴリAのみ）。オフラインでも動作。
- `--llm`: 精度改善のためAIを併用（カテゴリA＋B）。
- 未指定: 各フェーズの設定既定に従う（既定は両フェーズ無効）。

`orchestrator.py` の `config.effective_extraction_llm()` / `effective_structurize_llm()` が
実効値を解決し、抽出側（ステップ②のラベリング）と構造化側（ステップ③のルール補完）へ適用する。

## 6. まとめ（1枚図）

```
              cli.py（受付）           orchestrator.py（進行）
                  │                          │
   引数・設定を読む └───────────┐            │
                                ▼            ▼
   ① 抽出  pipeline.run_pipeline()  ── parsers/ + analyzers/（＋任意でLLM）
                                ▼
        抽出データ DXFDrawing
                                ▼
   ② 構造化  StructurizePipeline.run() ── associators/rule1..10（＋任意でLLM）
                                ▼
        構造化データ StructuredDrawing
                                ▼
   ③ 出力  serializers/  ──→  *_structured.json / *_structured.md（＋任意で *.json）
```

詳しい統合内容や処理分類は [`refactoring_result.md`](./refactoring_result.md) を参照。
