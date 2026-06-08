# dxf-extractor

DXFファイル（R12〜R2018）から形状・寸法・公差・表・注記・レイヤ情報を抽出・体系化し、構造化JSONとMarkdownレポートを生成するCLIツール。処理は **(a) 抽出フェーズ** と **(b) 体系化フェーズ** に分かれ、`dxf-extract` の3サブコマンド（`extract` / `structurize` / `run`）で個別にも連続にも実行できます。

```
DXFファイル ──→ ① 抽出 ──→ 抽出データ ──→ ② 構造化 ──→ 構造化データ ──→ ③ 出力
 (.dxf)              (DXFDrawing)              (StructuredDrawing)      (.json / .md)
```

① 形状・寸法・テキスト・表・レイヤを取り出し（`parsers/`・`analyzers/`）、② 10種類のルールで要素間の関係を判定し（`associators/`）、③ 構造化JSON（`*_structured.json`）とMarkdownレポート（`*_structured.md`）を出力します。LLMは**任意・補助的**に使われ、不使用でも全機能が完結します（[処理分類](#処理の3分類abc)）。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [`docs/summary.md`](docs/summary.md) | **まずはこれ**。全ドキュメントの要約（目次つき） |
| [`docs/processing_flow.md`](docs/processing_flow.md) | 全体像（DXF→抽出→構造化→出力）の入口ハブ |
| [`docs/extraction_details.md`](docs/extraction_details.md) | 各parser/analyzerの抽出内容・しきい値・実行順 |
| [`docs/structurization_rules.md`](docs/structurization_rules.md) | 全10ルール（全サブルール）の判定内容・出力 |
| [`docs/llm_usage.md`](docs/llm_usage.md) | LLMの利用箇所・制御・フォールバック・A/B/C分類 |
| [`docs/output_format.md`](docs/output_format.md) | 構造化JSONスキーマ・Markdown構成・終了コード |
| [`docs/extensibility_and_issues.md`](docs/extensibility_and_issues.md) | 拡張手順・設定パラメータ・既知の制限 |
| [`docs/refactoring_result.md`](docs/refactoring_result.md) | CLI統合・重複削減の記録 |

## 機能

- **形状抽出**: LINE / ARC / CIRCLE / POLYLINE / SPLINE / LEADER / HATCH / ELLIPSE などの幾何形状（LEADER・SPLINEはPolylineGeometry、HATCH・ELLIPSEはOtherGeometryとして記録）
- **寸法抽出**: DIMENSION エンティティおよびテキスト寸法
- **公差抽出**: 寸法・注記からの公差文字列のパース
- **表抽出**: 部品表などのテーブル構造の検出（LWPOLYLINEによる矩形テーブルおよびLINEエンティティの格子構造に対応）
- **注記抽出**: TEXT / MTEXT エンティティ（MTEXTの段落区切り `\P` を改行に変換）
- **レイヤ情報抽出**: レイヤ名・含有エンティティ種別・エンティティ数・用途分類（外形線 / 寸法線 / 中心線 / 補助線 / 注記 / 図枠 / その他）
- **論理ブロック検出**: DBSCANクラスタリングによる意味的なグループ化
- **図枠検出**: タイトルブロック・図枠の自動認識（レイヤ用途情報を優先利用し、面積比ヒューリスティックにフォールバック）
- **メタ情報抽出**: 図面番号・タイトル・改訂番号・尺度・作成者など（ラベルと値が同一テキスト内の形式と、別エンティティとして配置された近接テキスト形式の両方に対応）
- **LLM連携（オプション）**: ブロック種別・レイヤ用途の意味付け（OpenAI / Anthropic / Azure AI）
- **体系化**: 抽出データに10種類の関連付けルールを適用し、寸法・形状・表・注記の意味的な関連付けを `associations` フィールドに記録する
- **2フェーズ実行**: 抽出(a)と体系化(b)を `extract` / `structurize` / `run` の3サブコマンドで個別・連続に実行する。`run` はDXF入力から構造化JSON（`*_structured.json`）とMarkdownレポート（`*_structured.md`）までを一括生成する

### 体系化ルール（10種類）

抽出データに対し、依存関係を踏まえた順序で10ルールを適用します。各ルールの判定内容・しきい値・出力は [`docs/structurization_rules.md`](docs/structurization_rules.md) を参照。

| ルール | 内容 |
|---|---|
| Rule1 | 寸法↔形状マッチング（端点・円・ブロック帰属） |
| Rule2 | テキスト寸法分類（寸法線/テーブル番号） |
| Rule3 | テーブル構造化（境界・ヘッダー・列名） |
| Rule4 | 断面表示関連付け（断面記号↔断面図ブロック） |
| Rule5 | 注記↔形状対応（レイヤ・LEADER・近接） |
| Rule6 | 視図間投影関係（正面/上面/側面のグループ化） |
| Rule7 | ハッチング関連付け（境界形状・LEADER・断面） |
| Rule8 | 標題欄構造化（領域特定・ラベル-値ペア・NTS） |
| Rule9 | 改定情報・注記エリア抽出 |
| Rule10 | 部品番号紐づけ（部品ビュー・部品表行） |

### 多様な図面への汎用化（すべてオプトイン）

既定では従来挙動（日本語JIS・mm・モデルスペースのみ）と完全に一致し、`config.yaml` の設定で次を有効化できます。

- **多言語キーワード辞書**: レイヤ用途・標題欄ラベル・表ヘッダー・改定・断面のキーワードを追加/置換（`extraction.keywords`）。英語・独語など非日本語ラベルや独自命名規約に対応。
- **INSERT展開・複数シート**: ブロック参照を座標変換つきで展開し、ペーパースペース/複数シートも処理（`extraction.entity_source`）。各要素に帰属シート `sheet`、展開要素に由来ブロック `source_block` を付与。
- **単位・尺度の自動スケール**: 図面の外接範囲（＋`$INSUNITS`）から関連付けしきい値を自動スケールし、mm/inch/拡大図でも構造化を安定化（`structurize.scale`）。
- **作図規約プロファイル**: 標題欄位置・断面記号パターン・部品番号流儀（バルーン番号）を切替（`structurize.profile`）。

LLM不使用時（`--no-llm`）もルールベースで全機能が完結し、外部API呼び出しは発生しません（カテゴリAのみ）。

### 処理の3分類（A/B/C）

各処理はLLM使用の要否で分類されます。`--no-llm` 時は**カテゴリAのみ**を実行し、出力は従来と同等であることを退行テスト（`tests/integration/test_no_llm_regression.py`、`tests/fixtures/golden/` とのゴールデン比較）で担保しています。

| 分類 | 定義 | 該当 |
|---|---|---|
| **A: プログラムのみ** | LLM不要で完結 | 全抽出、Rule1/2/4/6/10、各ルールのフォールバック、シリアライズ |
| **B: LLMで精度改善** | プログラムでも可・LLMで向上 | ブロック種別/レイヤ用途のラベリング、Rule 3-1/5-3/7-2/8-2/9-2 |
| **C: LLM必須** | プログラム単独では困難 | 現状該当なし（将来の拡張枠。分類・文書化のみ） |

> LLM補完が失敗（APIキー未設定・通信エラー等）してもカテゴリA相当の結果へ安全に縮退するため、処理が止まることはありません。詳細は [`docs/llm_usage.md`](docs/llm_usage.md)。

## 必要環境

- Python 3.13以上
- [uv](https://docs.astral.sh/uv/)

## インストール

```powershell
uv sync
```

## 使い方

### dxf-extract（3サブコマンド: extract / structurize / run）

```powershell
# 連続実行 (a)+(b): DXF → 構造化JSON + Markdown を一気通貫生成
uv run dxf-extract run drawing.dxf

# サブコマンド省略時は config.yaml の execution.mode（既定 run）に従う（従来どおりの呼び方）
uv run dxf-extract drawing.dxf --no-llm

# (a) 抽出のみ: DXF → 抽出JSON <名前>.json
uv run dxf-extract extract drawing.dxf

# (b) 体系化のみ: 抽出JSON → 構造化JSON + Markdown
uv run dxf-extract structurize drawing.json

# 出力先指定 / 中間成果物（抽出JSON）も保存（run のみ）
uv run dxf-extract run drawing.dxf --output-dir output\ --save-intermediate
```

| サブコマンド | 入力 | 出力 |
|---|---|---|
| `extract` | `.dxf` | 抽出JSON `<名前>.json`（フェーズ(a)） |
| `structurize` | 抽出JSON | 構造化JSON `<名前>_structured.json` ＋ `<名前>_structured.md`（フェーズ(b)） |
| `run` | `.dxf` | 構造化JSON ＋ Markdown（＋ `--save-intermediate` で抽出JSON） |

| 共通オプション | 説明 | デフォルト |
|---|---|---|
| `--output-dir` | 成果物の出力先ディレクトリ | 入力ファイルと同じディレクトリ |
| `-c`, `--config` | 設定ファイルパス | `config.yaml`（存在する場合） |
| `-l`, `--log-level` | ログレベル `quiet` / `normal` / `verbose` | `normal` |
| `--llm` / `--no-llm` | LLMを有効/無効にする（対象は当該フェーズ） | config.yamlの設定値 |
| `--save-intermediate` | 中間成果物（抽出JSON）も保存する（`run`） | 保存しない |
| `--version` | バージョン表示 | - |

`extract`→`structurize` の2段実行の成果物は、`run` の連続実行の成果物と一致します。
LLM使用有無は `extraction.llm` / `structurize.llm` でフェーズ個別に指定でき、既定は両フェーズ無効です。
体系化ルールの有効/無効・適用順・パラメータは `structurize.rules_config`（外部JSON）で変更できます。

処理の流れや内部構造の詳細は [`docs/processing_flow.md`](docs/processing_flow.md) を参照。

### 終了コード

| コード | 意味 |
|---|---|
| 0 | 正常終了 |
| 1 | 一般エラー（出力書き込み失敗・処理中エラー） |
| 2 | 入力フォーマット不正（DXF読込/バージョン検証失敗、引数不正） |
| 3 | 設定ファイル不正 |

すべてのエラーメッセージは日本語で出力されます。

## 設定

`config.yaml` で動作をカスタマイズできます。

```yaml
dxf:
  supported_versions:
    min: "R12"
    max: "R2018"
  coordinate_normalization: false

execution:
  mode: run                # サブコマンド省略時の既定: extract / structurize / run

llm:
  # トップレベル llm は接続情報＋全体既定。各フェーズで個別指定しない限りこの enabled に従う。
  enabled: false
  provider: "openai"       # 利用環境の選択: openai / anthropic / azure（Azure AI Foundry）
  model: "gpt-5-mini"
  mode: "global"           # global / local
  priority: "accuracy"     # accuracy / token
  azure:                   # provider: "azure" のときのみ参照
    deployment: ""               # Azure AI Foundry のデプロイ名
    endpoint: ""                 # 例: https://<resource>.openai.azure.com/
    api_version: "2024-10-21"
    auth_method: "azure_cli"     # azure_cli（az login認証・APIキー不要）/ api_key

extraction:
  text_dimension:
    duplicate_threshold: 5.0   # テキスト寸法の重複判定距離
  clustering:
    epsilon: 20.0              # DBSCANのε（論理ブロック検出）
    min_samples: 2
  rules: []
  # llm:                       # 抽出フェーズのLLM上書き（未指定ならトップレベル llm.enabled を継承）
  #   enabled: false
  # structurize 側は structurize.llm（体系化フェーズの上書き）と
  # structurize.rules_config（体系化ルール設定JSONのパス、未指定なら現行構成）で制御
  # --- 汎用化（オプトイン。未指定なら従来挙動） ---
  keywords:                    # 多言語キーワード辞書（既定=現行と同一）
    merge_mode: merge          # merge（既定に追加）/ replace（指定カテゴリを置換）
    layer_purpose:
      外形線: [KONTUR, OUTLINE-MAIN]
      寸法線: [BEMASSUNG]
    title_block_labels:
      drawing_number: [Zeichnungsnr, "DWG-NO"]
      scale: [Massstab]
    table_headers: []
    revision: []
    section: []
  entity_source:               # INSERT展開・複数シート
    expand_inserts: false      # true で INSERT を座標変換つき展開
    max_depth: 5               # ネスト展開の最大深さ
    max_entities: 100000       # 展開後の累計上限（超過で安全打ち切り＋警告）
    process_paperspace: false  # true でペーパースペース/複数シートも処理

structurize:
  confidence_threshold: 0.0   # 信頼スコアフィルタ（0.0=全件採用）
  tolerances:
    delta: 2.0                 # 寸法端点マッチング許容誤差
    d_threshold: 5.0           # 注記-形状距離しきい値
    delta_y_ratio: 0.5         # テーブル同一行判定
  # --- 汎用化（オプトイン） ---
  scale:                       # 単位・尺度の自動スケール
    auto_scale: false          # true で $INSUNITS/外接範囲からしきい値を自動スケール
    base_unit: mm
    reference_size: null
  profile:                     # 作図規約プロファイル
    title_block_region: bottom # bottom / top / top_right / bottom_right / auto
    title_block_ratio: 0.2
    section_symbol_pattern: "^([A-Z])-\\1$|^[A-Z]$"  # 既定=A-A／単一英字
    part_number_style: integer_text  # integer_text / balloon / both
```

## LLM連携の設定

利用環境は `config.yaml` の `llm.provider`（`openai` / `anthropic` / `azure`）で選択します。

### OpenAI / Anthropic（APIキー）

`.env` ファイルにAPIキーを設定します。

```powershell
cp .env.example .env
# .env を編集してAPIキーを設定
```

```dotenv
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...
```

### Azure AI Foundry（Azure CLI 認証・APIキー不要）

`provider: azure` のときは、既定で **Azure CLI 認証**（`az login` で取得するAzure ADトークン）を使用します。APIキーは不要です。

```powershell
# 事前に一度ログインしておく（トークンは実行時に自動取得・更新される）
az login

# config.yaml で provider: azure, azure.deployment / endpoint を設定して実行
uv run dxf-extract run drawing.dxf --llm
```

```yaml
llm:
  provider: "azure"
  azure:
    deployment: "<your-deployment>"
    endpoint: "https://<resource>.openai.azure.com/"
    api_version: "2024-10-21"
    auth_method: "azure_cli"   # 既定。APIキーを使う場合は api_key
```

APIキー方式を使う場合は `auth_method: api_key` とし、`.env` に次を設定します。

```dotenv
# Azure AI Foundry（auth_method: api_key のときのみ）
AZURE_OPENAI_API_KEY=...
```

> Azure CLI 認証には `azure-identity` を使用します（`AzureCliCredential`）。トークンスコープは `https://cognitiveservices.azure.com/.default`。

## JSON出力スキーマ

既定で出力される **構造化JSON（`*_structured.json`）** は、抽出情報の全フィールドに加えて、
関連付け結果を `associations` フィールドに保持する。`--save-intermediate` で保存される
**抽出JSON（`<名前>.json`）** は `associations` を含まない同じ構造（中間成果物）である。

```jsonc
{
  "metadata": {
    "dxf_version": "R2018",
    "title": "部品図",
    "drawing_number": "DWG-001",
    "revision": "A",
    "scale": "1:1",
    "created_by": null,
    "designed_by": null,
    "checked_by": null,
    "approved_by": null,
    "material": null
  },
  "blocks": [...],        // 論理ブロック（DBSCANクラスタ）
  "shapes": [...],        // 幾何形状
  "dimensions": [...],    // DIMENSIONエンティティ
  "text_dimensions": [...],// テキストで記載された寸法
  "tolerances": [...],    // 公差
  "tables": [...],        // 表・部品表
  "notes": [...],         // 注記テキスト
  "layers": [...],        // レイヤ情報
  "associations": [       // 関連付け結果（構造化JSONのみ。抽出JSONには含まれない）
    {
      "rule": "1-1",            // 適用ルール番号
      "source_id": "...",       // 関連付け元エンティティID
      "target_ids": ["..."],    // 関連付け先エンティティID
      "confidence": 0.9,         // 信頼スコア
      "extracted_value": null,   // 抽出値（任意）
      "llm_augmented": false     // LLM補完されたか
    }
  ]
}
```

汎用化機能を有効にすると、任意フィールドが追加されます（**既定では出力されず**、従来スキーマと一致）。

| フィールド | 付与位置 | 有効化する設定 |
|---|---|---|
| `sheet` | `shapes` / `dimensions` / `notes` / `tables` の各要素 | `extraction.entity_source.process_paperspace` |
| `source_block` | `shapes[].geometry`（OtherGeometry） | `extraction.entity_source.expand_inserts` |
| `scale_context` | `metadata`（`{unit, factor, source}`） | `structurize.scale.auto_scale` |

## 開発

```powershell
# 依存関係のインストール
uv sync

# 全テストの実行
uv run pytest tests/ -v

# 単一テストの実行
uv run pytest tests/integration/test_pipeline.py -v -k test_run_pipeline

# パッケージの追加
uv add <package>
```

## 対応DXFバージョン

R12 〜 R2018（ezdxf がサポートする全バージョン）

## パフォーマンス

5MB以下のDXFファイルを10秒以内に処理することを目標としています。5MB超のファイルを入力した場合は警告を出力します。
