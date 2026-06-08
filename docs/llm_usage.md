# LLM利用の全容（範囲・対象・制御）

本書は、本プログラムが **どこで・何のために・どのようにLLMを使うか**、および
LLMを使わない場合との差を網羅する。

## 1. 制御: フェーズ個別スイッチ

LLM使用の有無は**フェーズごとに個別指定**できる（仕様 `specs/006-split-extract-structurize/`）。

- トップレベル `llm`: 接続情報（provider/model/azure 等）＋全体既定の `enabled`。
- `extraction.llm.enabled` / `structurize.llm.enabled`: 各フェーズの上書き。未指定（`None`）ならトップレベル `llm.enabled` を継承。
- 既定は両フェーズ無効（`config.yaml` の `llm.enabled: false`）。
- CLIの `--llm` / `--no-llm` は、起動サブコマンドの対象フェーズ（`extract`→抽出、`structurize`→体系化、`run`→両方）を上書きする。

実効値は `AppConfig.effective_extraction_llm()` / `effective_structurize_llm()` が解決し、
`orchestrator.run_extract` / `run_structurize` がそれぞれのフェーズへ適用する。

- `--no-llm`（または `enabled: false`）: 外部LLMを**一切呼ばない**（カテゴリAのみ）。オフライン動作可。
- `--llm`（または `enabled: true`）: カテゴリB処理でLLMを併用（精度改善）。

> 接続情報の真実源は引き続きトップレベル `llm` の1箇所（生成点 `llm/provider.create_llm` も単一）。フェーズ別ブロックが持つのは `enabled` の上書きのみ。

LLM無効時の出力が、リファクタリング前と同等であることは退行テストで担保している
（`tests/integration/test_no_llm_regression.py`）。

## 2. LLM接続の仕組み

| 要素 | 実装 | 内容 |
|------|------|------|
| 生成点 | `llm/provider.py` の `create_llm()` | **LLMを生成する唯一の関数**。LangChain `init_chat_model` を使用 |
| 利用環境の選択 | `config.llm.provider` | openai（直接）/ anthropic / azure（Azure AI Foundry） |
| 対応プロバイダ | openai / anthropic / azure | 既定モデル `gpt-5-mini`。azureは `azure.deployment`/`endpoint` 必須 |
| 認証（openai/anthropic） | `.env` のAPIキー | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` |
| 認証（azure） | `azure.auth_method` | 既定 `azure_cli`＝**Azure CLI 認証**（`az login` のAzure ADトークン、APIキー不要）。`api_key` 指定時のみ `AZURE_OPENAI_API_KEY` を使用 |
| プロンプト | `llm/prompts.py` | `PromptTemplate` で定義 |

`create_llm()` が単一の生成点であるため、LLM呼び出しの有無はこの関数の呼び出し回数で判定できる
（退行テスト・LLMスイッチテストはこれを利用）。

### 2-1. Azure AI Foundry（Azure CLI 認証）

`provider: azure` のとき、`azure.auth_method: azure_cli`（既定）では `azure-identity` の
`AzureCliCredential` からAzure ADトークンを取得し、`AzureChatOpenAI` の
`azure_ad_token_provider` として渡す（スコープ `https://cognitiveservices.azure.com/.default`）。
APIキーは不要で、事前に `az login` しておけばよい（トークンは実行時に遅延取得・更新）。
`azure.deployment` / `azure.endpoint` / `azure.api_version` を `config.yaml` で指定する。
`auth_method: api_key` を選ぶと、トークンプロバイダを渡さず環境変数 `AZURE_OPENAI_API_KEY` を使用する。

## 3. LLMを使う箇所（カテゴリB）

LLMは **限定的に・補助的に**使われる。大半の処理はカテゴリA（プログラムのみ）で完結する。

### 3-1. 抽出フェーズのラベリング（`llm/labeler.py`）

`run_pipeline(..., llm_enabled=...)` 内で、抽出フェーズの実効LLM（`effective_extraction_llm()`、未指定はトップレベル `llm.enabled` を継承）が有効なときのみ実行。

| 対象 | プロンプト | 出力 | フォールバック |
|------|-----------|------|----------------|
| 論理ブロックの種別 | `BLOCK_TYPE_PROMPT` | `part_view/sub_view/table/frame/notes` | 失敗時は元の種別（既定 `part_view`）を維持 |
| レイヤの用途 | `LAYER_PURPOSE_PROMPT` | `外形線/寸法線/中心線/補助線/注記/図枠/その他` | 失敗時は元の用途を維持 |

- ブロック・レイヤごとに1回 `llm.invoke()` を呼ぶ。失敗は個別に握りつぶし元の値を保持。
- `label_with_llm` 全体が例外を投げても、`run_pipeline` が警告ログを出してルールベース結果で継続する。

> **このラベリングは後段に大きく影響する**。ブロック種別 `table`/`notes` は**LLMでしか付与されない**ため、
> Rule8（標題欄＝最下端table）・Rule9-1（notesブロック）はLLM有効時に精度が上がる。
> LLM無効時はそれぞれ「下端20%エリア」「`Note(s)` ヘッダーテキスト」へのフォールバックで動作する。

### 3-2. 構造化フェーズのルール補完（`associators/llm_helper.py` の `try_llm_augment`）

LLMを使うのは以下の**5サブルールのみ**。いずれも `llm_config is not None` のときだけLLM経路に入る。

| サブルール | LLMにさせること | フォールバック（カテゴリA） |
|------------|------------------|------------------------------|
| 3-1 | テーブルのヘッダー行特定 | キーワード一致で特定した `row:idx` |
| 5-3 | 注記が指す形状の判定 | 最近傍の形状 |
| 7-2 | ハッチに対応するLEADERの特定 | 同一ブロック内のLEADER候補 |
| 8-2 | 標題欄ラベルに対応する値テキスト抽出 | 水平/垂直の近接探索で得た値 |
| 9-2 | 改定情報テキストの整形抽出 | 正規表現による行抽出 |

**LLMを使わないルール（純カテゴリA）**: Rule1, Rule2, Rule4, Rule6, Rule10。

### 3-3. フォールバックの一貫性

`try_llm_augment` は `LangChainException` / タイムアウト / 接続エラーを捕捉し、
**カテゴリA相当のフォールバック結果**（confidence 0.5、`llm_error=True`）を返す。
したがってAPIキー未設定・ネットワーク不通でも処理は止まらず、成果物は必ず生成される。

## 4. カテゴリ分類のまとめ（A / B / C）

| 分類 | 定義 | 該当 |
|------|------|------|
| **A: プログラムのみ** | LLM不要 | 全抽出（parsers/analyzers）、Rule1/2/4/6/10、各ルールのフォールバック、シリアライズ |
| **B: LLMで精度改善** | プログラムでも可、LLMで向上 | ラベリング（ブロック/レイヤ）、Rule 3-1/5-3/7-2/8-2/9-2 |
| **C: LLM必須** | プログラム単独では困難 | **現状該当なし**（将来の自然言語注記の意味解釈等を想定した枠組み。分類・文書化のみ） |

## 5. 未使用・拡張余地

- `prompts.py` の `FRAME_DETECTION_PROMPT`（図枠判定プロンプト）は定義済みだが**現状未使用**。
  図枠検出は `analyzers/frame_detector.py` がルールベースで行っている。LLMによる図枠判定を導入する余地。
- カテゴリC枠は未実装。追加する場合の方針は [拡張性と残課題](./extensibility_and_issues.md) を参照。

---

関連: [構造化ルール詳細](./structurization_rules.md) / [抽出フェーズ詳細](./extraction_details.md)
